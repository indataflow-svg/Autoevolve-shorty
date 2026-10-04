"""First-run state and action gates over isolated real sales/settings tables."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import core.sales_store as sales_store
import core.state as state
from app.api import app
from app.onboarding_api import StrategyInput


class OnboardingApiTests(unittest.TestCase):
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
        }, clear=False)
        self.env.start()
        self.client = TestClient(app)
        self.auth = ("founder", "dashboard-secret")
        self.headers = {"X-Founder-Action-Token": "action-secret"}
        self.website_research = patch("app.onboarding_api.extract_domain", new_callable=AsyncMock)
        self.website_research_mock = self.website_research.start()
        self.website_research_mock.return_value = {"pages": [], "pages_ok": 0}
        self.strategy_generator = patch("app.onboarding_api._generate_strategy_draft", new_callable=AsyncMock)
        self.strategy_generator_mock = self.strategy_generator.start()
        self.strategy_generator_mock.return_value = StrategyInput.model_validate(self.strategy_payload())

    def tearDown(self):
        self.strategy_generator.stop()
        self.website_research.stop()
        self.env.stop()
        state.DB_PATH = self.old_state
        sales_store.DB_PATH = self.old_sales
        self.temporary.cleanup()

    def post(self, suffix: str, payload: dict | None = None, *, token: bool = True):
        return self.client.post(
            f"/company/setup/onboarding/{suffix}", auth=self.auth,
            headers=self.headers if token else {}, json=payload,
        )

    def start(self):
        response = self.post("company", {
            "name": "Example Studio", "website": "https://studio.test",
            "objective": "Find qualified operations buyers", "market": "United States",
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response

    def confirm(self):
        response = self.post("company/confirm", {
            "name": "Example Studio", "website": "https://studio.test",
            "description": "Example Studio builds operations tools.",
            "industry": "Software", "positioning": "Operations teams get clear records.",
            "offer_summary": "A guided operations workflow.",
        })
        self.assertEqual(response.status_code, 200, response.text)

    @staticmethod
    def strategy_payload():
        return {
            "name": "First outbound", "objective": "Find qualified operations buyers",
            "success_metric": "Qualified replies per month", "offers": ["Workflow audit"],
            "icp": {"industry": "Software", "description": "Midmarket teams with manual operations handoffs", "company_sizes": ["50-500"]},
            "buyer_titles": ["Operations Director"], "markets": ["United States"],
            "positive_signals": ["Growing operations team"], "exclusions": [],
            "tone": "Direct and factual", "approved_claims": ["Guided setup"],
            "prohibited_claims": ["Guaranteed revenue"], "channels": ["email", "linkedin"],
        }

    def strategy(self):
        drafted = self.post("strategy/draft")
        self.assertEqual(drafted.status_code, 200, drafted.text)
        self.assertEqual(drafted.json()["program"]["strategy_draft"]["offers"], ["Workflow audit"])
        response = self.post("strategy", self.strategy_payload())
        self.assertEqual(response.status_code, 200, response.text)

    def test_strategy_requires_generated_draft_and_caches_it(self):
        self.start()
        self.confirm()
        self.assertEqual(self.post("strategy", self.strategy_payload()).status_code, 409)
        first = self.post("strategy/draft")
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["next_step"], "strategy")
        self.assertEqual(first.json()["program"]["strategy_draft"]["icp"]["industry"], "Software")
        self.assertEqual(self.post("strategy/draft").status_code, 200)
        self.strategy_generator_mock.assert_awaited_once()
        edited = self.strategy_payload()
        edited["tone"] = "Warm and precise"
        saved = self.post("strategy", edited)
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()["program"]["strategy"]["tone"], "Warm and precise")

    def test_auth_action_gates_validation_and_resume(self):
        self.assertEqual(self.client.get("/company/ui/onboarding").status_code, 401)
        empty = self.client.get("/company/ui/onboarding", auth=self.auth)
        self.assertEqual(empty.json()["next_step"], "company")
        denied = self.post("company", {"name": "Example Studio", "website": "https://studio.test", "objective": "Qualified buyers", "market": "US"}, token=False)
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(self.post("company", {"name": "X", "website": "bad", "objective": "a", "market": "U"}).status_code, 422)
        self.start()
        resumed = self.client.get("/company/ui/onboarding", auth=self.auth)
        self.assertEqual(resumed.json()["next_step"], "research_company")
        self.assertEqual(resumed.json()["program"]["company"]["name"], "Example Studio")
        with patch.dict(os.environ, {"CE_API_KEY": "", "PDL_API_KEY": ""}):
            unavailable = self.post("research-company")
        self.assertEqual(unavailable.status_code, 409)
        self.assertIn("No company enrichment provider", self.client.get("/company/ui/onboarding", auth=self.auth).json()["program"]["research_error"])
        self.confirm()  # Manual confirmation is honest when provider is unavailable.
        self.assertEqual(self.client.get("/company/ui/onboarding", auth=self.auth).json()["next_step"], "strategy")

    def test_company_research_distinguishes_no_match_from_provider_block(self):
        from services.company_enrich import CompanyEnrichError
        from services.pdl import PeopleDataLabsError

        self.start()
        with patch.dict(os.environ, {"CE_API_KEY": "test-only", "PDL_API_KEY": "test-only"}):
            with patch("services.company_enrich.CompanyEnrichClient") as ce_client, \
                 patch("services.pdl.PeopleDataLabsClient") as pdl_client:
                ce_client.return_value.enrich_company.side_effect = CompanyEnrichError("not found", 404)
                pdl_client.return_value.enrich_company.side_effect = PeopleDataLabsError("not found", 404)
                missing = self.post("research-company")
                self.assertEqual(missing.status_code, 404, missing.text)
                self.assertIn("no matching company", missing.json()["detail"])
                ce_client.return_value.enrich_company.side_effect = CompanyEnrichError("blocked", 403)
                blocked = self.post("research-company")
        self.assertEqual(blocked.status_code, 424, blocked.text)
        self.assertIn("companyenrich blocked API access", blocked.json()["detail"])
        self.assertIn("pdl has no matching company", blocked.json()["detail"])
        self.assertNotIn("method=GET", blocked.json()["detail"])
        self.assertEqual(self.client.get("/company/ui/onboarding", auth=self.auth).json()["next_step"], "research_company")
        self.confirm()

    def test_company_research_uses_website_without_provider_keys(self):
        self.start()
        self.website_research_mock.return_value = {
            "domain": "studio.test", "base_url": "https://studio.test", "pages_ok": 1,
            "pages": [{"ok": True, "url": "https://studio.test", "site_name": "Example Studio",
                       "description": "Example Studio builds practical operations software for teams.", "text": ""}],
        }
        with patch.dict(os.environ, {"CE_API_KEY": "", "PDL_API_KEY": ""}):
            researched = self.post("research-company")
        self.assertEqual(researched.status_code, 200, researched.text)
        program = researched.json()["program"]
        self.assertEqual(program["research_provider"], "website")
        self.assertEqual(program["company_research"]["description"], "Example Studio builds practical operations software for teams.")
        self.assertEqual(program["company_research"]["sources"][0]["url"], "https://studio.test")
        self.assertEqual(researched.json()["next_step"], "confirm_company")

    def test_website_research_survives_blocked_and_missing_enrichment(self):
        from services.company_enrich import CompanyEnrichError
        from services.pdl import PeopleDataLabsError

        self.start()
        self.website_research_mock.return_value = {
            "domain": "studio.test", "base_url": "https://studio.test", "pages_ok": 1,
            "pages": [{"ok": True, "url": "https://studio.test", "site_name": "Example Studio",
                       "description": "Example Studio builds practical operations software for teams.", "text": ""}],
        }
        with patch.dict(os.environ, {"CE_API_KEY": "test-only", "PDL_API_KEY": "test-only"}):
            with patch("services.company_enrich.CompanyEnrichClient") as ce_client, \
                 patch("services.pdl.PeopleDataLabsClient") as pdl_client:
                ce_client.return_value.enrich_company.side_effect = CompanyEnrichError("blocked", 403)
                pdl_client.return_value.enrich_company.side_effect = PeopleDataLabsError("not found", 404)
                researched = self.post("research-company")
        self.assertEqual(researched.status_code, 200, researched.text)
        self.assertEqual(researched.json()["program"]["research_provider"], "website")
        self.assertEqual(researched.json()["next_step"], "confirm_company")

    def test_research_rejects_unsafe_website_before_provider_calls(self):
        self.start()
        self.website_research_mock.side_effect = ValueError("website resolves to a non-public address")
        with patch.dict(os.environ, {"CE_API_KEY": "test-only"}):
            with patch("services.company_enrich.CompanyEnrichClient") as client:
                response = self.post("research-company")
        self.assertEqual(response.status_code, 422)
        client.assert_not_called()

    def test_website_research_ignores_mismatched_provider_company(self):
        self.start()
        self.website_research_mock.return_value = {
            "domain": "studio.test", "base_url": "https://studio.test", "pages_ok": 1,
            "pages": [{"ok": True, "url": "https://studio.test", "site_name": "Example Studio",
                       "description": "Example Studio builds practical operations software for teams.", "text": ""}],
        }
        with patch.dict(os.environ, {"CE_API_KEY": "test-only", "PDL_API_KEY": ""}):
            with patch("services.company_enrich.CompanyEnrichClient") as client:
                client.return_value.extract_company_profile.return_value = {
                    "name": "Different Company", "domain": "different.example.org", "industry": "Finance",
                }
                researched = self.post("research-company")
        self.assertEqual(researched.status_code, 200, researched.text)
        program = researched.json()["program"]
        self.assertEqual(program["research_provider"], "website")
        self.assertEqual(program["company_research"]["name"], "Example Studio")
        self.assertIsNone(program["company_research"]["industry"])

    def test_full_calibration_reuses_real_candidates_contacts_and_drafts(self):
        self.start()
        with patch.dict(os.environ, {"CE_API_KEY": "test-only"}):
            with patch("services.company_enrich.CompanyEnrichClient") as client:
                client.return_value.enrich_company.return_value = {"company": {"name": "Example Studio"}}
                client.return_value.extract_company_profile.return_value = {
                    "name": "Example Studio", "description": "Saved provider company profile",
                    "industry": "Software", "signals": {"summary_line": "Operations workflows"},
                    "specialties": ["Operations tools"],
                }
                researched = self.post("research-company")
        self.assertEqual(researched.status_code, 200, researched.text)
        self.assertEqual(researched.json()["program"]["research_provider"], "companyenrich")
        self.confirm()
        self.strategy()
        candidate_a, _ = sales_store.upsert_lead({
            "company": "Acme Systems", "company_domain": "acme.test", "source": "prospeo",
            "country": "United States", "metadata": {"company_candidate": True},
        })
        candidate_b, _ = sales_store.upsert_lead({
            "company": "Other Systems", "company_domain": "other.test", "source": "apollo",
            "country": "Canada", "metadata": {"company_candidate": True},
        })
        summary = {"results": [{"lead": candidate_a}, {"lead": candidate_b}], "warnings": [], "providers": {"prospeo": 2}}
        with patch("app.onboarding_api.research_market_leads", return_value=summary):
            searched = self.post("search")
        self.assertEqual(searched.status_code, 200, searched.text)
        self.assertEqual(len(searched.json()["sample"]), 2)
        self.assertEqual(self.post("calibration", {"feedback": [{"lead_id": "unknown", "rating": "good"}]}).status_code, 422)
        good = self.post("calibration", {"feedback": [{"lead_id": candidate_a["id"], "rating": "good"}]})
        self.assertEqual(good.json()["next_step"], "calibrate")
        self.assertEqual(self.client.get("/company/ui/onboarding", auth=self.auth).json()["program"]["feedback"][candidate_a["id"]]["rating"], "good")
        bad = self.post("calibration", {"feedback": [{"lead_id": candidate_b["id"], "rating": "bad", "reason": "wrong_geography"}]})
        self.assertEqual(bad.json()["next_step"], "refinement")
        self.assertIn("country:Canada", bad.json()["program"]["proposed_refinement"]["exclusions"])
        approved = self.post("refinement", {"approved": True})
        self.assertEqual(approved.json()["next_step"], "buyers")
        self.assertIn("country:Canada", approved.json()["program"]["strategy"]["exclusions"])
        contact, _ = sales_store.upsert_lead({
            "email": "buyer@acme.test", "full_name": "Buyer One", "job_title": "Operations Director",
            "company": "Acme Systems", "company_domain": "acme.test", "source": "hunter",
        })
        self.assertEqual(self.post("buyer", {"candidate_lead_id": candidate_a["id"], "existing_contact_id": candidate_b["id"]}).status_code, 422)
        buyer = self.post("buyer", {"candidate_lead_id": candidate_a["id"], "existing_contact_id": contact["id"]})
        self.assertEqual(buyer.status_code, 200, buyer.text)
        self.assertEqual(buyer.json()["next_step"], "drafts")
        from services.sales_service import _draft_lead_context
        context = _draft_lead_context(sales_store.get_lead(contact["id"]))
        self.assertEqual(context["program_strategy"]["approved_claims"], ["Guided setup"])
        self.assertEqual(context["program_strategy"]["prohibited_claims"], ["Guaranteed revenue"])

        async def saved_draft(lead_id):
            return sales_store.create_draft(lead_id, "A real draft", "Hello, this is a saved draft for review.")

        with patch("app.onboarding_api.build_draft", side_effect=saved_draft):
            drafted = self.post("draft", {"candidate_lead_id": candidate_a["id"]})
        self.assertEqual(drafted.status_code, 200, drafted.text)
        self.assertEqual(drafted.json()["next_step"], "activate")
        draft_id = drafted.json()["program"]["draft_ids"][candidate_a["id"]]
        self.assertEqual(sales_store.get_draft(draft_id)["status"], "draft")
        activated = self.post("activate")
        self.assertEqual(activated.status_code, 200, activated.text)
        self.assertEqual(activated.json()["next_step"], "home")
        self.assertEqual(self.client.get("/company/ui/onboarding", auth=self.auth).json()["program"]["status"], "activated")
        self.assertEqual(self.post("activate").status_code, 409)

    def test_healthy_empty_search_and_all_rejected_sample_can_retry(self):
        self.start()
        self.confirm()
        self.strategy()
        with patch("app.onboarding_api.research_market_leads", return_value={
            "results": [], "providers": {"prospeo": 0, "apollo": 0, "lusha": 0},
            "warnings": ["prospeo: unavailable"],
        }):
            empty = self.post("search")
        self.assertEqual(empty.status_code, 200, empty.text)
        self.assertEqual(empty.json()["next_step"], "search")
        self.assertEqual(empty.json()["sample"], [])
        with patch("app.onboarding_api.research_market_leads", return_value={
            "results": [], "providers": {"prospeo": 0, "apollo": 0},
            "warnings": ["prospeo: unavailable", "apollo: unavailable"],
        }):
            failed = self.post("search")
        self.assertEqual(failed.status_code, 502)
        self.assertEqual(self.client.get("/company/ui/onboarding", auth=self.auth).json()["next_step"], "search")
        candidate, _ = sales_store.upsert_lead({
            "company": "Wrong Fit", "company_domain": "wrong.test", "source": "prospeo",
            "metadata": {"company_candidate": True},
        })
        with patch("app.onboarding_api.research_market_leads", return_value={
            "results": [{"lead": candidate}], "providers": {"prospeo": 1}, "warnings": [],
        }):
            self.assertEqual(self.post("search").status_code, 200)
        rated = self.post("calibration", {"feedback": [{"lead_id": candidate["id"], "rating": "bad", "reason": "weak_signal"}]})
        self.assertEqual(rated.json()["next_step"], "refinement")
        decision = self.post("refinement", {"approved": False})
        self.assertEqual(decision.status_code, 200, decision.text)
        self.assertEqual(decision.json()["next_step"], "search")
