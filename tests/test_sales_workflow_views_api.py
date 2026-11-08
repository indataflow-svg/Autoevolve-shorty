"""Replies and meetings expose saved sales facts without inferred intent or booking state."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api import app
import core.sales_store as sales_store
import core.state as state


def test_replies_and_meeting_markers_are_typed_paginated_and_gated():
    with tempfile.TemporaryDirectory() as directory:
        old_state, old_sales = state.DB_PATH, sales_store.DB_PATH
        state.DB_PATH = sales_store.DB_PATH = Path(directory) / "sales.db"
        try:
            state.init_db()
            sales_store.init_sales_db()
            first, _ = sales_store.upsert_lead({"full_name": "Alex Carter", "email": "alex@rift.test", "company": "Rift Dynamics", "source": "manual"})
            second, _ = sales_store.upsert_lead({"full_name": "Priya Shah", "email": "priya@luma.test", "company": "Luma Logistics", "source": "manual"})
            sales_store.mark_replied(first["id"], "Re: Operations", "Please share more details.", "<reply-1@test>")
            sales_store.add_interaction(first["id"], "outbound", "email", "outreach", "Follow-up", "Thanks for your reply")
            sales_store.mark_replied(second["id"], "Re: Timing", "Can we discuss timing?", "<reply-2@test>")
            with patch.dict(os.environ, {"DASHBOARD_USER": "founder", "DASHBOARD_PASSWORD": "secret", "SALES_ACTION_TOKEN": "action"}):
                client = TestClient(app)
                auth = ("founder", "secret")
                assert client.get("/company/ui/replies").status_code == 401
                replies = client.get("/company/ui/replies?sort=company&page_size=1", auth=auth)
                assert replies.status_code == 200, replies.text
                assert replies.json()["total"] == 2
                assert replies.json()["counts"]["latest"] == 1
                assert replies.json()["items"][0]["body"] == "Can we discuss timing?"
                assert replies.json()["items"][0]["can_draft_reply"] is True
                earlier = client.get("/company/ui/replies?q=Rift", auth=auth).json()["items"][0]
                assert earlier["is_latest_interaction"] is False
                assert earlier["can_draft_reply"] is False
                assert client.get(f"/company/ui/replies/{earlier['id']}", auth=auth).status_code == 200
                with sales_store.connect() as connection:
                    # Move the earlier reply ahead of the outbound follow-up so it
                    # is the latest interaction again. A far-future date keeps this
                    # true regardless of when the suite runs.
                    connection.execute("UPDATE sales_interactions SET created_at = ? WHERE id = ?", ("2099-10-01T10:00:00Z", earlier["id"]))
                assert sales_store.get_lead(first["id"])["latest_interaction"]["id"] == earlier["id"]
                assert client.get(f"/company/ui/replies/{earlier['id']}", auth=auth).json()["can_draft_reply"] is True
                assert client.get("/company/ui/replies/99999", auth=auth).status_code == 404
                assert client.get("/company/ui/replies?view=Positive", auth=auth).status_code == 422

                assert client.get("/company/ui/meetings", auth=auth).json()["items"] == []
                url = f"/company/sales/leads/{first['id']}/schedule-meeting"
                payload = {"scheduled_for": "2026-10-02T10:00:00Z", "note": "Discuss workflow"}
                assert client.post(url, auth=auth, json=payload).status_code == 403
                assert client.post(url, auth=auth, headers={"X-Founder-Action-Token": "action"}, json={"note": "x" * 401}).status_code == 422
                recorded = client.post(url, auth=auth, headers={"X-Founder-Action-Token": "action"}, json=payload)
                assert recorded.status_code == 200, recorded.text
                assert recorded.json()["lead"]["metadata"]["meeting"]["status"] == "scheduled"
                meetings = client.get("/company/ui/meetings?view=dated", auth=auth)
                assert meetings.status_code == 200, meetings.text
                assert meetings.json()["counts"] == {"total": 1, "dated": 1, "undated": 0, "awaiting": 0, "with_note": 1}
                assert meetings.json()["items"][0]["scheduled_for"] == payload["scheduled_for"]
                assert meetings.json()["items"][0]["note"] == payload["note"]
                assert meetings.json()["items"][0]["source"] == "manual"
                assert client.get(f"/company/ui/meetings/{first['id']}", auth=auth).status_code == 200
                assert client.get("/company/ui/meetings/missing", auth=auth).status_code == 404
                assert client.get("/company/ui/meetings?sort=Soonest", auth=auth).status_code == 422
        finally:
            state.DB_PATH, sales_store.DB_PATH = old_state, old_sales


def test_form_submissions_reach_replies_and_drive_the_booking_flow():
    """A hosted or external form submission lands in Replies as clean answers
    with the meeting-request action; the emailed contact choosing a slot on the
    public booking page is what records the scheduled meeting."""
    import core.form_store as form_store

    with tempfile.TemporaryDirectory() as directory:
        old_state, old_sales, old_forms = state.DB_PATH, sales_store.DB_PATH, form_store.DB_PATH
        state.DB_PATH = sales_store.DB_PATH = form_store.DB_PATH = Path(directory) / "sales.db"
        try:
            state.init_db()
            sales_store.init_sales_db()
            form_store.init_form_db()
            form_store.seed_default_form()
            with patch.dict(os.environ, {
                "DASHBOARD_USER": "founder", "DASHBOARD_PASSWORD": "secret",
                "SALES_ACTION_TOKEN": "action", "SALES_INTAKE_SECRET": "intake-secret",
                # No Resend configuration: the meeting request must save the
                # request and report the missing send path honestly.
                "SALES_FROM_EMAIL": "", "SALES_RESEND_DOMAIN": "",
            }):
                client = TestClient(app)
                auth = ("founder", "secret")
                action = {"X-Founder-Action-Token": "action"}

                # The seeded hosted form renders and accepts a submission.
                page = client.get("/f/contact")
                assert page.status_code == 200, page.text
                assert 'name="email"' in page.text
                submitted = client.post(
                    "/f/contact",
                    data={"full_name": "Sam Lee", "email": "sam@acme.test", "company": "Acme", "message": "Need a demo"},
                    follow_redirects=False,
                )
                assert submitted.status_code == 303
                # The honeypot answers like success and writes nothing.
                spam = client.post("/f/contact", data={"email": "bot@spam.test", "website": "spam"}, follow_redirects=False)
                assert spam.status_code == 303
                assert sales_store.get_lead_by_email("bot@spam.test") is None

                # The submission appears in Replies as a form channel answer set.
                listed = client.get("/company/ui/replies?view=submissions", auth=auth).json()
                assert listed["counts"]["submissions"] == 1
                item = listed["items"][0]
                assert item["channel"] == "form"
                assert item["answers"]["Full name"] == "Sam Lee"
                assert item["answers"]["What are you looking for?"] == "Need a demo"
                # A form submission has no email thread: drafting stays email-only.
                assert item["can_draft_reply"] is False
                detail = client.get(f"/company/ui/replies/{item['id']}", auth=auth).json()
                assert detail["form_slug"] == "contact"
                lead_id = item["lead_id"]

                # The meeting request is gated and records an awaiting state.
                assert client.post(f"/company/sales/leads/{lead_id}/meeting-request", json={"slots": ["Tue 10:00"]}, auth=auth).status_code == 403
                empty = client.post(f"/company/sales/leads/{lead_id}/meeting-request", json={"slots": ["  "]}, auth=auth, headers=action)
                assert empty.status_code == 422
                requested = client.post(
                    f"/company/sales/leads/{lead_id}/meeting-request",
                    json={"slots": ["Tue 10:00", "Wed 14:00"], "note": "Happy to walk through pricing"},
                    auth=auth, headers=action,
                )
                assert requested.status_code == 200, requested.text
                body = requested.json()
                assert body["ok"] is True
                assert body["status"] == "awaiting_booking"
                # Unconfigured Resend: honest warning, request kept.
                assert body["email_sent"] is False
                assert "not sent" in body["warning"]
                # The lead stage does not move until a slot is chosen.
                assert sales_store.get_lead(lead_id)["stage"] != "scheduled"

                meetings = client.get("/company/ui/meetings?view=awaiting", auth=auth).json()
                assert meetings["counts"]["awaiting"] == 1
                assert meetings["items"][0]["slots"] == ["Tue 10:00", "Wed 14:00"]

                # The public booking page lists the offered slots and only a
                # listed slot records the meeting.
                booking = client.get(f"/book/{lead_id}")
                assert booking.status_code == 200
                assert "Tue 10:00" in booking.text and "Wed 14:00" in booking.text
                assert client.get("/book/lead_missing").status_code == 200  # renders the invalid-link state
                bad = client.post(f"/book/{lead_id}", data={"slot": "9"})
                assert "not on this offer" in bad.text
                confirmed = client.post(f"/book/{lead_id}", data={"slot": "1"})
                assert confirmed.status_code == 200
                assert "You're confirmed" in confirmed.text
                lead = sales_store.get_lead(lead_id)
                assert lead["metadata"]["meeting"]["status"] == "scheduled"
                assert lead["metadata"]["meeting"]["scheduled_for"] == "Wed 14:00"
                assert lead["metadata"]["meeting"]["source"] == "booking_link"
                assert lead["stage"] == "scheduled"
                # The chosen meeting shows as booked, not awaiting.
                dated = client.get("/company/ui/meetings?view=dated", auth=auth).json()
                assert dated["items"][0]["status"] == "scheduled"
                assert dated["items"][0]["source"] == "booking_link"
                # Re-opening the page states it is already confirmed.
                assert "Already confirmed" in client.get(f"/book/{lead_id}").text

                # An external tool can post the same shape with the shared secret.
                external = client.post(
                    "/integrations/leads/form",
                    json={"form": "contact", "answers": {"full_name": "Zed", "email": "zed@z.test", "role": "CTO"}},
                    headers={"X-Company-Core-Lead-Secret": "intake-secret"},
                )
                assert external.status_code == 200, external.text
                assert external.json()["form"] == "contact"
                assert sales_store.get_lead_by_email("zed@z.test") is not None
                # Without the secret the endpoint refuses; unknown slugs 404.
                assert client.post("/integrations/leads/form", json={"email": "x@y.z"}).status_code == 401
                assert client.post(
                    "/integrations/leads/form", json={"form": "nope", "answers": {"email": "x@y.z"}},
                    headers={"X-Company-Core-Lead-Secret": "intake-secret"},
                ).status_code == 404

                # Form management is authenticated and founder-gated.
                created = client.post("/company/commercial/forms", json={
                    "slug": "demo-request", "name": "Book a demo",
                    "fields": [{"key": "full_name", "label": "Name", "type": "text", "required": True},
                               {"key": "email", "label": "Email", "type": "email", "required": True}],
                }, auth=auth, headers=action)
                assert created.status_code == 200, created.text
                assert created.json()["hosted_path"] == "/f/demo-request"
                assert client.get("/f/demo-request").status_code == 200
                assert client.post("/company/commercial/forms", json={
                    "slug": "demo-request", "name": "dup", "fields": [{"key": "a", "label": "A"}],
                }, auth=auth, headers=action).status_code == 409
                disabled = client.patch("/company/commercial/forms/demo-request", json={"active": False}, auth=auth, headers=action)
                assert disabled.status_code == 200 and disabled.json()["active"] is False
                assert client.get("/f/demo-request").status_code == 404

                # The intake config exposes everything an external tool needs on
                # one screen: the absolute endpoint plus the secret when set.
                assert client.get("/company/commercial/forms/config").status_code == 401
                config = client.get("/company/commercial/forms/config", auth=auth).json()
                assert config["endpoint_url"].endswith("/integrations/leads/form")
                assert config["secret_header"] == "X-Company-Core-Lead-Secret"
                assert config["secret"] == "intake-secret"
                assert config["secret_configured"] is True
        finally:
            state.DB_PATH, sales_store.DB_PATH, form_store.DB_PATH = old_state, old_sales, old_forms
