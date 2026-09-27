import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import core.marketing_store as marketing_store
import core.sales_store as sales_store
import core.state as state
from app.api import app
from fastapi.testclient import TestClient


class OperationsUiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary.name) / "company.db"
        self.old_state_path = state.DB_PATH
        self.old_marketing_path = marketing_store.DB_PATH
        self.old_sales_path = sales_store.DB_PATH
        state.DB_PATH = self.database
        marketing_store.DB_PATH = self.database
        sales_store.DB_PATH = self.database
        state.init_db()
        marketing_store.init_marketing_db()
        sales_store.init_sales_db()
        self.project = state.create_org("Example Company", "company-core", env_prefix="BUFFER_")
        state.set_active_org(self.project["id"])
        self.env = patch.dict(os.environ, {
            "DASHBOARD_USER": "founder",
            "DASHBOARD_PASSWORD": "dashboard-secret",
        }, clear=False)
        self.env.start()
        self.client = TestClient(app)
        self.auth = ("founder", "dashboard-secret")

    def tearDown(self):
        self.env.stop()
        state.DB_PATH = self.old_state_path
        marketing_store.DB_PATH = self.old_marketing_path
        sales_store.DB_PATH = self.old_sales_path
        self.temporary.cleanup()

    def test_old_workflow_page_urls_redirect_to_modern_pages(self):
        for old, modern in (
            ("/operations", "/home"),
            ("/operations/sales/email", "/outreach"),
            ("/operations/marketing", "/campaigns"),
            ("/operations/marketing/campaigns", "/campaigns"),
            ("/operations/marketing/assets", "/content"),
        ):
            response = self.client.get(old, follow_redirects=False)
            self.assertEqual(response.status_code, 307, old)
            self.assertEqual(response.headers["location"], modern)

    def test_replaced_operator_routes_preserve_compatibility_redirects(self):
        for old, modern in (
            ("/legacy/operations", "/home"),
            ("/operations/sales", "/research"),
            ("/operations/sales/discovery", "/research"),
            ("/legacy/operations/sales/email", "/outreach"),
            ("/legacy/operations/marketing", "/campaigns"),
            ("/legacy/operations/marketing/campaigns", "/campaigns"),
            ("/legacy/operations/marketing/assets", "/content"),
            ("/operations/marketing/publishing", "/content"),
        ):
            response = self.client.get(old, follow_redirects=False)
            self.assertEqual(response.status_code, 307, old)
            self.assertEqual(response.headers["location"], modern)

    def test_root_and_retired_history_redirect_without_legacy_html(self):
        for path in ("/", "/operations/history"):
            response = self.client.get(path, follow_redirects=False)
            self.assertEqual(response.status_code, 307)
            self.assertEqual(response.headers["location"], "/home")
        self.assertEqual(self.client.post("/", data={"message": "old command"}, auth=self.auth).status_code, 405)

    def test_public_booking_pages_remain_available(self):
        self.assertEqual(self.client.get("/meet").status_code, 200)
        self.assertEqual(self.client.get("/calendar").status_code, 200)

    def test_redirects_preserve_query_state_and_canonicalize_slashes(self):
        for path, target, status in (
            ("/?view=latest", "/home?view=latest", 307),
            ("/operations/sales/email?status=draft&page=2", "/outreach?status=draft&page=2", 307),
            ("/contacts/?contact=abc%3A123", "/contacts?contact=abc%3A123", 308),
        ):
            response = self.client.get(path, follow_redirects=False)
            self.assertEqual(response.status_code, status)
            self.assertEqual(response.headers["location"], target)

    def test_missing_api_routes_never_return_spa_html(self):
        for path in ("/company/ui/missing", "/company/Sales/contacts", "/assets/missing.js", "/static/cockpit.js"):
            response = self.client.get(path, headers={"Accept": "text/html"})
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json(), {"detail": "Not Found"})

    def test_missing_browser_page_has_true_404_and_react_document(self):
        fixture_build = Path(self.temporary.name) / "dist"
        fixture_build.mkdir()
        (fixture_build / "index.html").write_text('<div id="root"></div>')
        with patch("app.api._ui_dist", fixture_build):
            response = self.client.get("/missing-page", headers={"Accept": "text/html"})
        self.assertEqual(response.status_code, 404)
        self.assertIn('id="root"', response.text)

    def test_operations_overview_returns_unified_history(self):
        task = state.create_task(org_id=self.project["id"], agent="growth", task_type="campaign", input_text="Create campaign")
        campaign = marketing_store.create_campaign(
            org_id=self.project["id"],
            task_id=task["id"],
            request="Create campaign",
            objective="awareness",
            buyer="ops_manager",
            topic="document handoffs",
            social_platforms=["instagram", "x"],
            video_platform="shorts",
        )
        lead, _ = sales_store.upsert_lead({"email": "ops@example.com", "company": "Example Logistics", "source": "website", "consent": True})
        sales_store.add_event(lead["id"], "lead.reviewed", {"status": "qualified"})
        sales_store.mark_replied(lead["id"], "Re: Walkthrough", "Interested", "<reply-1@example.com>")

        with patch.dict(os.environ, {"DASHBOARD_PASSWORD": "dashboard-secret"}, clear=False):
            with patch("app.company_ops_api.marketing_doctor", return_value={"ok": True, "checks": {}}), patch("app.company_ops_api.sales_doctor", return_value={"ok": True, "checks": {}}):
                response = self.client.get("/company/operations/overview", auth=self.auth)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["active_org"]["slug"], "company-core")
        self.assertEqual(len(body["marketing_campaigns"]), 1)
        self.assertEqual(len(body["sales_leads"]), 1)
        domains = {item["domain"] for item in body["history"]}
        self.assertIn("marketing", domains)
        self.assertIn("sales", domains)

    def test_direct_campaign_launcher_creates_and_spawns_campaign(self):
        payload = {
            "objective": "awareness",
            "brief": "Freight teams keep working from outdated shipping document versions across handoffs.",
            "social_platforms": ["instagram", "x"],
            "video_platform": "shorts",
            "voice_mode": "tts",
            "voice_transcript": "",
        }
        with patch.dict(os.environ, {"DASHBOARD_PASSWORD": "dashboard-secret"}, clear=False):
            with patch("app.marketing_api.spawn") as spawn:
                response = self.client.post("/company/marketing/campaigns", auth=self.auth, json=payload)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["campaign"]["topic"], payload["brief"])
        self.assertEqual(body["campaign"]["voice_mode"], "tts")
        self.assertEqual(body["campaign"]["buyer"], "logistics operators")
        spawn.assert_called_once()
        campaigns = marketing_store.list_campaigns(limit=5, org_id=self.project["id"])
        self.assertEqual(len(campaigns), 1)

    def test_manual_carousel_post_creation_and_attribution(self):
        with patch.dict(os.environ, {
            "DASHBOARD_PASSWORD": "dashboard-secret",
            "MARKETING_FORMS_BASE_URL": "https://forms.example.com",
        }, clear=False):
            session = self.client.post(
                "/company/marketing/manual-posts/session",
                auth=self.auth,
                json={"platform": "instagram"},
            )
        self.assertEqual(session.status_code, 200)
        created = session.json()["post"]
        self.assertEqual(created["workflow_status"], "uploading")
        self.assertEqual(created["asset_count"], 0)

        with patch.dict(os.environ, {"DASHBOARD_PASSWORD": "dashboard-secret"}, clear=False):
            uploaded = self.client.post(
                f"/company/marketing/manual-posts/{created['id']}/assets",
                auth=self.auth,
                files={"asset": ("workflow-gaps-slide1.png", b"fakepng", "image/png")},
            )
        self.assertEqual(uploaded.status_code, 200)
        uploaded_post = uploaded.json()["post"]
        self.assertEqual(uploaded_post["asset_count"], 1)
        self.assertEqual(uploaded_post["workflow_status"], "uploading")

        with patch.dict(os.environ, {
            "DASHBOARD_PASSWORD": "dashboard-secret",
            "MARKETING_FORMS_BASE_URL": "https://forms.example.com",
        }, clear=False):
            finalized = self.client.post(
                f"/company/marketing/manual-posts/{created['id']}/finalize",
                auth=self.auth,
            )
        self.assertEqual(finalized.status_code, 200)
        body = finalized.json()
        self.assertTrue(body["ok"])
        post = body["post"]
        self.assertTrue(post["post_id"].startswith("instagram_carousel_"))
        self.assertEqual(post["campaign_id"], "mkt_instagram_carousel_202609")
        self.assertEqual(post["workflow_status"], "ready")
        self.assertTrue(post["buffer_ready"])
        self.assertIn("utm_source=instagram", post["tracked_url"])
        self.assertIn("forms.example.com", post["tracked_url"])
        self.assertIn("Link in bio", post["caption"])
        self.assertEqual(post["assets"][0]["filename"], "workflow-gaps-slide1.png")

        sales_store.upsert_lead({
            "email": "carousel@example.com",
            "company": "Example Logistics",
            "source": "social_form",
            "post_id": post["post_id"],
            "campaign_id": post["campaign_id"],
            "utm_campaign": post["utm_campaign"],
            "consent": True,
        })
        with patch.dict(os.environ, {"DASHBOARD_PASSWORD": "dashboard-secret"}, clear=False):
            listed = self.client.get("/company/marketing/manual-posts", auth=self.auth)
        self.assertEqual(listed.status_code, 200)
        listed_post = listed.json()["posts"][0]
        self.assertEqual(listed_post["attribution"]["leads"], 1)

    def test_manual_carousel_can_push_ready_post_to_buffer(self):
        with patch.dict(os.environ, {"DASHBOARD_PASSWORD": "dashboard-secret"}, clear=False):
            session = self.client.post(
                "/company/marketing/manual-posts/session",
                auth=self.auth,
                json={"platform": "instagram"},
            )
        created = session.json()["post"]
        with patch.dict(os.environ, {"DASHBOARD_PASSWORD": "dashboard-secret"}, clear=False):
            self.client.post(
                f"/company/marketing/manual-posts/{created['id']}/assets",
                auth=self.auth,
                files={"asset": ("workflow-gaps-slide1.png", b"fakepng", "image/png")},
            )
            self.client.post(
                f"/company/marketing/manual-posts/{created['id']}/finalize",
                auth=self.auth,
            )
        fake_output = {"ok": True, "provider": "buffer", "results": [{"platform": "instagram", "status": "draft_confirmed", "post_id": "buf_123"}]}
        with patch.dict(os.environ, {
            "DASHBOARD_PASSWORD": "dashboard-secret",
            "MARKETING_G3_BIN": str(Path(__file__)),
        }, clear=False):
            with patch("app.marketing_api._run", return_value='prefix {"ok": true} suffix'), patch("app.marketing_api._last_json", return_value=fake_output):
                response = self.client.post(
                    f"/company/marketing/manual-posts/{created['id']}/buffer-draft",
                    auth=self.auth,
                )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["post"]["buffer_status"], "drafted")
        self.assertEqual(body["post"]["workflow_status"], "buffer_draft")
        default_result = body["result"].get("default", {})
        self.assertEqual(default_result.get("results", [{}])[0].get("post_id"), "buf_123")

    def test_manual_video_uses_controlled_link_and_creates_buffer_handoff(self):
        project_root = Path(self.temporary.name) / "projects"
        with patch.dict(os.environ, {
            "DASHBOARD_PASSWORD": "dashboard-secret",
            "MARKETING_G3_BIN": str(Path(__file__)),
        }, clear=False), \
             patch("app.marketing_api.PROJECTS_ROOT", project_root):
            session = self.client.post(
                "/company/marketing/manual-posts/session",
                auth=self.auth,
                json={
                    "platform": "x",
                    "post_type": "video",
                    "destination_url": "offers.example.com/ops-checklist",
                    "link_label": "operations checklist",
                },
            )
            self.assertEqual(session.status_code, 200)
            created = session.json()["post"]
            self.assertEqual(created["post_type"], "video")
            self.assertTrue(created["post_id"].startswith("x_video_"))
            self.assertTrue(created["destination_url"].startswith("https://offers.example.com/"))
            self.assertIn("utm_medium=video", created["tracked_url"])

            uploaded = self.client.post(
                f"/company/marketing/manual-posts/{created['id']}/assets",
                auth=self.auth,
                files={"asset": ("visibility-demo.mp4", b"\x00\x00\x00\x18ftypmp42", "video/mp4")},
            )
            self.assertEqual(uploaded.status_code, 200)

            finalized = self.client.post(
                f"/company/marketing/manual-posts/{created['id']}/finalize",
                auth=self.auth,
            )
            self.assertEqual(finalized.status_code, 200)
            post = finalized.json()["post"]
            self.assertEqual(post["asset_count"], 1)
            self.assertIn("Get the operations checklist", post["caption"])
            self.assertIn(post["tracked_url"], post["caption"])

            fake_output = {
                "ok": True,
                "provider": "buffer",
                "results": [{"platform": "x", "status": "draft_confirmed", "post_id": "buf_video"}],
            }
            with patch("app.marketing_api._run", return_value='{"ok": true}'), \
                 patch("app.marketing_api._last_json", return_value=fake_output):
                pushed = self.client.post(
                    f"/company/marketing/manual-posts/{created['id']}/buffer-draft",
                    auth=self.auth,
                )
            self.assertEqual(pushed.status_code, 200)
            handoff = Path(post["asset_dir"]) / "g3_manual_handoff.json"
            payload = json.loads(handoff.read_text())
            self.assertEqual(payload["drafts"][0]["thread"][0]["media"][0]["path"], "visibility-demo.mp4")
if __name__ == "__main__":
    unittest.main()
