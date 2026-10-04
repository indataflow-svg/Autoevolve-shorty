"""Service-first contact discovery runs without company onboarding."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import core.sales_store as sales_store
import core.state as state
from app.api import app
from app.service_discovery_api import ServiceSearchPlan


class ServiceDiscoveryApiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.old_state = state.DB_PATH
        self.old_sales = sales_store.DB_PATH
        db = Path(self.temporary.name) / "company.db"
        state.DB_PATH = sales_store.DB_PATH = db
        state.init_db()
        sales_store.init_sales_db()
        self.env = patch.dict(os.environ, {
            "DASHBOARD_USER": "founder", "DASHBOARD_PASSWORD": "dashboard-secret",
            "SALES_ACTION_TOKEN": "action-secret", "SALES_SEND_RECONCILE_ON_STARTUP": "false",
        })
        self.env.start()
        self.client = TestClient(app)
        self.auth = ("founder", "dashboard-secret")
        self.headers = {"X-Founder-Action-Token": "action-secret"}
        self.planner = patch("app.service_discovery_api._plan_service", new_callable=AsyncMock)
        self.plan = self.planner.start()
        self.plan.return_value = ServiceSearchPlan(
            buyer_industry="Dental clinics", search_keywords=["dental practice", "appointment scheduling"],
            buyer_titles=["Practice Manager"],
            rationale="Dental clinics may need help with appointment scheduling.",
        )

    def tearDown(self):
        self.planner.stop()
        self.env.stop()
        state.DB_PATH = self.old_state
        sales_store.DB_PATH = self.old_sales
        self.temporary.cleanup()

    def post(self, path: str, body: dict, *, token: bool = True):
        return self.client.post(
            f"/company/setup/service-discovery/{path}", auth=self.auth,
            headers=self.headers if token else {}, json=body,
        )

    def test_service_and_count_find_contacts_then_resume_and_retarget(self):
        self.assertEqual(self.client.get("/company/ui/service-discovery").status_code, 401)
        self.assertEqual(self.client.get("/company/ui/service-discovery", auth=self.auth).json()["runs"], [])
        payload = {"service": "Appointment scheduling for dental clinics", "desired_contacts": 2}
        self.assertEqual(self.post("search", payload, token=False).status_code, 403)
        self.assertEqual(self.post("search", {**payload, "desired_contacts": 26}).status_code, 422)
        first, _ = sales_store.upsert_lead({
            "full_name": "Alex Lee", "job_title": "Practice Manager", "company": "Bright Dental",
            "company_domain": "bright.test", "source": "apollo", "metadata": {"service_discovery_preview": True},
        })
        second, _ = sales_store.upsert_lead({
            "full_name": "Sam Rivera", "job_title": "Practice Manager", "company": "Clear Dental",
            "company_domain": "clear.test", "source": "prospeo", "metadata": {"service_discovery_preview": True},
        })

        def search(*, keywords, buyer_titles, market, desired_contacts):
            self.assertEqual(keywords, ["dental practice", "appointment scheduling"])
            self.assertEqual((buyer_titles, market, desired_contacts), (["Practice Manager"], None, 2))
            return {"results": [first, second], "providers": {"apollo": 1, "prospeo": 1}, "completed_providers": ["apollo", "prospeo"], "warnings": []}

        with patch("app.service_discovery_api.search_service_contacts", side_effect=search):
            created = self.post("search", payload)
        self.assertEqual(created.status_code, 200, created.text)
        run = created.json()["runs"][0]
        self.assertEqual(run["status"], "searched")
        self.assertEqual(run["desired_contacts"], 2)
        self.assertEqual(run["contact_ids"], [first["id"], second["id"]])
        self.assertEqual(run["contacts"][0]["name"], "Alex Lee")
        self.assertEqual(run["contacts"][1]["source"], "prospeo")
        self.assertEqual(run["plan"]["search_keywords"], ["dental practice", "appointment scheduling"])
        self.plan.assert_awaited_once()
        self.assertIsNone(state.get_onboarding_program())
        resumed = self.client.get("/company/ui/service-discovery", auth=self.auth)
        self.assertEqual(resumed.json()["runs"][0]["id"], run["id"])

        with patch("app.service_discovery_api.search_service_contacts", return_value={
            "results": [], "providers": {"apollo": 0}, "completed_providers": ["apollo"],
            "warnings": ["prospeo local 24-hour search cap reached"],
        }) as search_again:
            retargeted = self.post(f"{run['id']}/search", {
                "buyer_industry": "Veterinary clinics", "search_keywords": ["veterinary practice"],
                "buyer_titles": ["Clinic Manager"], "market": "Canada", "desired_contacts": 3,
            })
        self.assertEqual(retargeted.status_code, 200, retargeted.text)
        search_again.assert_called_once_with(
            keywords=["veterinary practice"], buyer_titles=["Clinic Manager"],
            market="Canada", desired_contacts=3,
        )
        self.assertEqual(retargeted.json()["runs"][0]["status"], "no_results")
        self.assertEqual(retargeted.json()["runs"][0]["contacts"], [])
        self.plan.assert_awaited_once()

    def test_provider_failures_are_visible_without_invented_contacts(self):
        with patch("app.service_discovery_api.search_service_contacts", return_value={
            "results": [], "providers": {"apollo": 0, "prospeo": 0}, "completed_providers": [],
            "warnings": ["apollo unavailable", "prospeo local cap reached"],
        }):
            response = self.post("search", {
                "service": "Appointment scheduling for dental clinics", "desired_contacts": 4,
            })
        self.assertEqual(response.status_code, 200, response.text)
        run = response.json()["runs"][0]
        self.assertEqual(run["status"], "provider_error")
        self.assertEqual(run["contacts"], [])
        self.assertEqual(len(run["warnings"]), 2)
