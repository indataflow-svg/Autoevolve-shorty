import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.api import app
import core.sales_store as sales_store
import core.state as state


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class LinkedInOutreachTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary.name) / "company.db"
        self.old_state_path = state.DB_PATH
        self.old_sales_path = sales_store.DB_PATH
        state.DB_PATH = self.database
        sales_store.DB_PATH = self.database
        state.init_db()
        sales_store.init_sales_db()
        self.client = TestClient(app)
        self.auth = ("founder", "dashboard-secret")

    def tearDown(self):
        state.DB_PATH = self.old_state_path
        sales_store.DB_PATH = self.old_sales_path
        self.temporary.cleanup()

    def _lead(self, **overrides):
        payload = {"full_name": "Aline Ops", "job_title": "Ops Lead", "company": "Example Co",
                   "company_domain": "example.com", "source": "prospeo"}
        payload.update(overrides)
        lead, _ = sales_store.upsert_lead(payload)
        return lead

    def test_contact_profile_surfaces_linkedin_url(self):
        lead = self._lead()
        sales_store.merge_lead_metadata(lead["id"], {
            "contact_resolution": {"details": {"linkedin_url": "https://www.linkedin.com/in/aline-ops"}}
        })
        stored = sales_store.get_lead(lead["id"])
        profile = stored["contact_profile"]
        self.assertEqual(profile["linkedin_url"], "https://www.linkedin.com/in/aline-ops")
        self.assertTrue(profile["linkedin_ready"])
        self.assertTrue(profile["ready_for_outreach"])

    def test_discover_linkedin_prefers_apollo(self):
        from services.linkedin_discovery import discover_linkedin

        lead = self._lead(email="aline@example.com")
        with patch("services.linkedin_discovery.ApolloClient") as apollo_cls:
            apollo_cls.return_value.match_person.return_value = {
                "linkedin_url": "https://www.linkedin.com/in/aline-ops"}
            result = discover_linkedin(lead["id"])
        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "apollo")
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["linkedin_url"], "https://www.linkedin.com/in/aline-ops")
        stored = sales_store.get_lead(lead["id"])
        self.assertTrue(stored["contact_profile"]["linkedin_ready"])

    def test_discover_linkedin_falls_back_to_prospeo(self):
        from services.linkedin_discovery import discover_linkedin

        lead = self._lead(metadata={"prospeo_person_id": "person_1"})
        with patch("services.linkedin_discovery.ApolloClient") as apollo_cls, \
                patch("services.linkedin_discovery.ProspeoClient") as prospeo_cls:
            apollo_cls.return_value.match_person.return_value = {}
            apollo_cls.return_value.people_search.return_value = []
            prospeo_cls.return_value.enrich_person.return_value = {
                "linkedin_url": "https://www.linkedin.com/in/aline-ops"}
            result = discover_linkedin(lead["id"])
        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "prospeo")
        self.assertEqual(result["linkedin_url"], "https://www.linkedin.com/in/aline-ops")

    def test_discover_linkedin_uses_cache_without_provider_calls(self):
        from services.linkedin_discovery import discover_linkedin

        lead = self._lead()
        sales_store.merge_lead_metadata(lead["id"], {
            "contact_resolution": {"details": {"linkedin_url": "https://www.linkedin.com/in/aline-ops",
                                               "linkedin_provider": "apollo"}}
        })
        with patch("services.linkedin_discovery.ApolloClient") as apollo_cls, \
                patch("services.linkedin_discovery.ProspeoClient") as prospeo_cls:
            result = discover_linkedin(lead["id"])
            apollo_cls.assert_not_called()
            prospeo_cls.assert_not_called()
        self.assertTrue(result["cached"])
        self.assertEqual(result["linkedin_url"], "https://www.linkedin.com/in/aline-ops")

    def test_preview_linkedin_invite_uses_model_then_stores_copy(self):
        from agents.linkedin import LinkedInDM, LinkedInInvite
        from services.sales_service import build_linkedin_draft, preview_linkedin_draft

        lead = self._lead()
        sales_store.merge_lead_metadata(lead["id"], {
            "contact_resolution": {"details": {"linkedin_url": "https://www.linkedin.com/in/aline-ops"}}
        })
        invite = LinkedInInvite(note="Hi Aline — mind if I connect?", rationale="test")
        with patch("agents.linkedin.draft_linkedin_outreach", new=AsyncMock(return_value=invite)):
            preview = _run(preview_linkedin_draft(lead["id"], "invite"))
        self.assertTrue(preview["ok"])
        self.assertEqual(preview["provider"], "model")
        self.assertEqual(preview["preview"]["text"], "Hi Aline — mind if I connect?")
        self.assertEqual(preview["profile_url"], "https://www.linkedin.com/in/aline-ops")

        dm1 = LinkedInDM(text="Hi Aline, thanks for connecting.", rationale="test")
        with patch("agents.linkedin.draft_linkedin_outreach", new=AsyncMock(return_value=dm1)):
            draft = _run(build_linkedin_draft(lead["id"], "dm1"))
        self.assertEqual(draft["channel"], "linkedin")
        self.assertEqual(draft["kind"], "linkedin_dm1")
        self.assertIn("https://www.linkedin.com/in/aline-ops", draft["body"])

    def test_preview_linkedin_falls_back_without_model(self):
        from services.sales_service import preview_linkedin_draft

        lead = self._lead()
        sales_store.merge_lead_metadata(lead["id"], {
            "contact_resolution": {"details": {"linkedin_url": "https://www.linkedin.com/in/aline-ops"}}
        })
        with patch("agents.linkedin.draft_linkedin_outreach", new=AsyncMock(side_effect=RuntimeError("no key"))):
            preview = _run(preview_linkedin_draft(lead["id"], "dm1"))
        self.assertEqual(preview["provider"], "fallback")
        self.assertTrue(preview["preview"]["text"])

    def test_linkedin_endpoints_require_profile_and_validate_piece(self):
        lead = self._lead()
        with patch.dict(os.environ, {
            "DASHBOARD_USER": "founder",
            "DASHBOARD_PASSWORD": "dashboard-secret",
            "SALES_ACTION_TOKEN": "action-secret",
        }, clear=False):
            headers = {"X-Founder-Action-Token": "action-secret"}
            missing = self.client.post(
                f"/company/sales/leads/{lead['id']}/linkedin-preview?piece=invite",
                auth=self.auth, headers=headers)
            self.assertEqual(missing.status_code, 409)

            sales_store.merge_lead_metadata(lead["id"], {
                "contact_resolution": {"details": {"linkedin_url": "https://www.linkedin.com/in/aline-ops"}}
            })
            with patch("agents.linkedin.draft_linkedin_outreach",
                        new=AsyncMock(side_effect=RuntimeError("no key"))):
                ok = self.client.post(
                    f"/company/sales/leads/{lead['id']}/linkedin-preview?piece=dm1",
                    auth=self.auth, headers=headers)
            self.assertEqual(ok.status_code, 200)
            self.assertEqual(ok.json()["channel"], "linkedin")

            bad_piece = self.client.post(
                f"/company/sales/leads/{lead['id']}/linkedin-preview?piece=nudge",
                auth=self.auth, headers=headers)
            self.assertEqual(bad_piece.status_code, 409)


if __name__ == "__main__":
    unittest.main()
