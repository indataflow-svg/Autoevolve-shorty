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
                    connection.execute("UPDATE sales_interactions SET created_at = ? WHERE id = ?", ("2026-10-01T10:00:00Z", earlier["id"]))
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
                assert meetings.json()["counts"] == {"total": 1, "dated": 1, "undated": 0, "with_note": 1}
                assert meetings.json()["items"][0]["scheduled_for"] == payload["scheduled_for"]
                assert meetings.json()["items"][0]["note"] == payload["note"]
                assert meetings.json()["items"][0]["source"] == "manual"
                assert client.get(f"/company/ui/meetings/{first['id']}", auth=auth).status_code == 200
                assert client.get("/company/ui/meetings/missing", auth=auth).status_code == 404
                assert client.get("/company/ui/meetings?sort=Soonest", auth=auth).status_code == 422
        finally:
            state.DB_PATH, sales_store.DB_PATH = old_state, old_sales
