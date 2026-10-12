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


class ServiceSeedingTests(unittest.TestCase):
    """A service search seeds the canonical context without clobbering it."""

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
            buyer_industry="Dental clinics", search_keywords=["dental practice"],
            buyer_titles=["Practice Manager"],
            rationale="Dental clinics may need help with appointment scheduling.",
        )

    def tearDown(self):
        self.planner.stop()
        self.env.stop()
        state.DB_PATH = self.old_state
        sales_store.DB_PATH = self.old_sales
        self.temporary.cleanup()

    def search(self, **extra):
        return self.client.post(
            "/company/setup/service-discovery/search", auth=self.auth,
            headers=self.headers,
            json={"service": "Appointment scheduling for dental clinics", "desired_contacts": 2, **extra},
        )

    def test_search_seeds_a_minimal_context_and_leaves_the_rest_unknown(self):
        from core.company_context import get_company_context

        self.assertIsNone(get_company_context())
        with patch("app.service_discovery_api.search_service_contacts", return_value={
            "results": [], "providers": {"apollo": 0}, "completed_providers": ["apollo"], "warnings": [],
        }):
            response = self.search()
        self.assertEqual(response.status_code, 200, response.text)
        context = get_company_context()
        assert context is not None
        self.assertEqual(context.product.name, "Appointment scheduling for dental clinics")
        self.assertEqual(context.customer.industry, "Dental clinics")
        self.assertEqual(context.customer.buyer_roles, ["Practice Manager"])
        self.assertEqual(context.state.marketing_stage, "starting_from_zero")
        # Seeding invents nothing: the founder has not answered these yet.
        self.assertIsNone(context.customer.ideal_customer)
        self.assertIsNone(context.market.problem)
        self.assertIsNone(context.objective.primary_goal)
        self.assertEqual(context.status, "context_incomplete")

    def test_optional_company_name_is_seeded_when_given(self):
        from core.company_context import get_company_context

        with patch("app.service_discovery_api.search_service_contacts", return_value={
            "results": [], "providers": {}, "completed_providers": [], "warnings": [],
        }):
            self.assertEqual(self.search(company_name="Bright Dental Co").status_code, 200)
        context = get_company_context()
        assert context is not None
        self.assertEqual(context.company.name, "Bright Dental Co")

    def test_discovered_contacts_are_recorded_as_demand_evidence(self):
        from core.company_context import get_company_context

        lead, _ = sales_store.upsert_lead({
            "full_name": "Alex Lee", "company": "Bright Dental",
            "company_domain": "bright.test", "source": "apollo",
        })
        with patch("app.service_discovery_api.search_service_contacts", return_value={
            "results": [lead], "providers": {"apollo": 1}, "completed_providers": ["apollo"], "warnings": [],
        }):
            self.assertEqual(self.search().status_code, 200)
        context = get_company_context()
        assert context is not None
        self.assertEqual(context.evidence.existing_demand, ["1 prospect contact discovered via apollo"])

    def test_seeding_never_overwrites_confirmed_answers(self):
        from core.company_context import (
            get_company_context, normalize_company_context, save_company_context,
        )

        save_company_context(normalize_company_context({
            "company": {"name": "Confirmed Co"},
            "product": {"name": "Confirmed product"},
            "customer": {"ideal_customer": "Confirmed buyers", "industry": "Logistics"},
        }))
        with patch("app.service_discovery_api.search_service_contacts", return_value={
            "results": [], "providers": {}, "completed_providers": [], "warnings": [],
        }):
            self.assertEqual(self.search(company_name="Other Co").status_code, 200)
        context = get_company_context()
        assert context is not None
        self.assertEqual(context.company.name, "Confirmed Co")
        self.assertEqual(context.product.name, "Confirmed product")
        self.assertEqual(context.customer.industry, "Logistics")
        # Empty fields are still filled from the search.
        self.assertEqual(context.customer.buyer_roles, ["Practice Manager"])
        self.assertEqual(context.state.marketing_stage, "starting_from_zero")

    def test_seeding_failure_never_breaks_the_search(self):
        with patch("app.service_discovery_api.search_service_contacts", return_value={
            "results": [], "providers": {}, "completed_providers": [], "warnings": [],
        }), patch("core.company_context.seed_from_service", side_effect=RuntimeError("db gone")):
            response = self.search()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["runs"][0]["status"], "provider_error")
