"""Prospecting inside governance: search from evidence, attribute up to the ceiling.

Reads cost provider credits but contact nobody, so the action is governed
like a draft (capped, attributed, refused without a ceiling) rather than
like a send. Terms come from evidence at validate time and are recorded in
the step config; nothing is guessed at run time.
"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import core.state as state
from app.api import app
from core import commercial_store, marketing_store, sales_store, workflow_store
from core.company_context import normalize_company_context, save_company_context
from core.evidence import resolve_research_terms
from core.plan_governance import normalize_method, validate_plan
from core.validation_plan import (
    GroundingReport,
    PlanProvenance,
    ValidationPlan,
    WORKFLOW_TEMPLATE,
    build_plan_record,
    save_validation_plan,
)
from core.workflow_store import GOVERNED_ACTIONS, READ_ACTIONS
from services.workflow_actions import research_prospects
from tests.market_validation_fixtures import (
    NORTHLIGHT_CONTEXT,
    NORTHLIGHT_PLAN,
    plan_with_validation,
)


def provenance() -> PlanProvenance:
    return PlanProvenance(
        prompt_version=WORKFLOW_TEMPLATE,
        prompt_path="prompts/market_validation_v1.md",
        model_route="reasoning",
        model_name="auto/best-reasoning",
        model_provider="omniroute",
    )


MOCK_RESULTS = {
    "results": [
        {"lead": {"id": "lead_new1", "company": "New One",
                  "company_domain": "new1.test"}, "created": True},
        {"lead": {"id": "lead_new2", "company": "New Two",
                  "company_domain": "new2.test"}, "created": True},
        {"lead": {"id": "lead_old", "company": "Old Co",
                  "company_domain": "old.test"}, "created": False},
    ],
    "providers": {"prospeo": 2, "apollo": 1},
    "warnings": [],
}


class ResearchBase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self._paths = (state.DB_PATH, workflow_store.DB_PATH,
                       marketing_store.DB_PATH, sales_store.DB_PATH,
                       commercial_store.DB_PATH)
        state.DB_PATH = base / "company.db"
        commercial_store.DB_PATH = state.DB_PATH
        workflow_store.DB_PATH = base / "workflows.db"
        marketing_store.DB_PATH = sales_store.DB_PATH = base / "company.db"
        state.init_db()
        marketing_store.init_marketing_db()
        sales_store.init_sales_db()
        workflow_store.init_db()
        commercial_store.init_commercial_db()
        self.context = normalize_company_context(NORTHLIGHT_CONTEXT)
        save_company_context(self.context)
        self.env = patch.dict(os.environ, {
            "DASHBOARD_USER": "founder", "DASHBOARD_PASSWORD": "dashboard-secret",
            "SALES_ACTION_TOKEN": "action-secret",
            "SALES_SEND_RECONCILE_ON_STARTUP": "false",
        }, clear=False)
        self.env.start()
        self.client = TestClient(app)
        self.auth = ("founder", "dashboard-secret")
        self.headers = {"X-Founder-Action-Token": "action-secret"}

    def tearDown(self):
        self.env.stop()
        (state.DB_PATH, workflow_store.DB_PATH, marketing_store.DB_PATH,
         sales_store.DB_PATH, commercial_store.DB_PATH) = self._paths
        self.temporary.cleanup()

    def store_plan(self, plan: dict) -> str:
        record = build_plan_record(
            ValidationPlan.model_validate(plan), provenance(), GroundingReport())
        return save_validation_plan(record).id

    def govern(self, plan: dict):
        candidate = ValidationPlan.model_validate(plan)
        return validate_plan(candidate, self.context, plan_id=self.store_plan(plan))[0]

    def config(self, **extra) -> dict:
        base = {"industry": "logistics", "location": "United States",
                "industry_source": "test", "max_contacts": 50}
        base.update(extra)
        return base


class TermResolutionTests(ResearchBase):
    def test_validated_icp_industry_wins(self):
        icp = self.client.post("/company/commercial/icps", auth=self.auth, headers=self.headers, json={
            "name": "Logi", "status": "validated",
            "criteria": [{"field": "industry", "operator": "equals", "value": "freight"}],
        }).json()
        self.assertEqual(icp["status"], "validated")
        terms = resolve_research_terms()
        self.assertEqual(terms["industry"], "freight")
        self.assertTrue(terms["industry_source"].startswith("validated_icp:"))

    def test_top_evidence_is_used_and_marked_assumption(self):
        self.client.post("/company/commercial/accounts", auth=self.auth, headers=self.headers,
                         json={"company_name": "Alpha Co", "industry": "logistics"})
        self.client.post("/company/commercial/accounts", auth=self.auth, headers=self.headers,
                         json={"company_name": "Beta Co", "industry": "logistics"})
        terms = resolve_research_terms()
        self.assertEqual(terms["industry"], "logistics")
        self.assertEqual(terms["industry_source"], "top_evidence_industry")

    def test_nothing_resolvable_blocks_with_reason(self):
        with self.assertRaisesRegex(ValueError, "validate an ICP"):
            resolve_research_terms()


class ResearchActionTests(ResearchBase):
    def test_new_candidates_attributed_up_to_ceiling(self):
        with patch("services.sales_service.research_market_leads", return_value=MOCK_RESULTS):
            result = research_prospects({"plan_id": "plan_1", "workflow_id": "wf_1"},
                                        self.config(max_contacts=1))
        output = result["output"]
        self.assertEqual(output["attributed"], 1)
        self.assertEqual(output["skipped_known"], 1)
        self.assertEqual(output["over_ceiling"], 1)
        self.assertEqual(output["providers_queried"], {"prospeo": 2, "apollo": 1})
        self.assertEqual(output["sent"], 0)
        self.assertIsNone(output["validation_events"])
        self.assertIs(output["external_side_effects"], False)
        self.assertEqual(result["metrics"]["candidates_new"], 1)

    def test_without_ceiling_it_researches_nothing(self):
        with patch("services.sales_service.research_market_leads",
                   side_effect=AssertionError("must not search")):
            result = research_prospects({}, self.config(max_contacts=0))
        self.assertEqual(result["output"]["attributed"], 0)
        self.assertEqual(result["output"]["candidates_found"], 0)

    def test_missing_industry_is_refused(self):
        with self.assertRaisesRegex(ValueError, "resolved industry"):
            research_prospects({}, self.config(industry="  "))

    def test_governance_maps_discovery_methods(self):
        self.assertEqual(normalize_method("prospecting"), "prospect_discovery")
        self.assertEqual(normalize_method("Market Research"), "prospect_discovery")
        self.assertIn("research_prospects", GOVERNED_ACTIONS)
        self.assertIn("research_prospects", READ_ACTIONS)


class ResearchGovernanceTests(ResearchBase):
    def discovery_plan(self) -> dict:
        return plan_with_validation(method="prospect_discovery", channel="email",
                                    message="Researching the market.")

    def test_discovery_resolves_terms_into_the_step(self):
        self.client.post("/company/commercial/icps", auth=self.auth, headers=self.headers, json={
            "name": "Logi", "status": "validated",
            "criteria": [{"field": "industry", "operator": "equals", "value": "freight"}],
        })
        decision = self.govern(self.discovery_plan())
        self.assertEqual(decision.status, "valid")
        (step,) = decision.resolved_actions
        self.assertEqual(step.action, "research_prospects")
        self.assertEqual(step.config["industry"], "freight")
        self.assertTrue(step.config["industry_source"].startswith("validated_icp:"))
        self.assertEqual(step.config["max_contacts"], 50)

    def test_discovery_blocks_without_any_evidence(self):
        decision = self.govern(self.discovery_plan())
        self.assertEqual(decision.status, "blocked")
        self.assertTrue(any("validate an ICP" in r for r in decision.reasons), decision.reasons)

    def test_discovery_run_writes_attributed_candidates(self):
        self.client.post("/company/commercial/icps", auth=self.auth, headers=self.headers, json={
            "name": "Logi", "status": "validated",
            "criteria": [{"field": "industry", "operator": "equals", "value": "freight"}],
        })
        self.store_plan(self.discovery_plan())
        created = self.client.post("/company/automation/governance", auth=self.auth,
                                   headers=self.headers, json={})
        self.assertEqual(created.status_code, 200, created.text)
        self.assertEqual(created.json()["resolved_actions"][0]["action"], "research_prospects")
        self.client.post("/company/automation/governance/approve", auth=self.auth,
                         headers=self.headers, json={})
        with patch("services.sales_service.research_market_leads", return_value=MOCK_RESULTS):
            executed = self.client.post("/company/automation/governance/run", auth=self.auth,
                                        headers=self.headers, json={})
        self.assertEqual(executed.status_code, 200, executed.text)
        execution = executed.json()["execution"]
        step = execution["steps"][0]
        self.assertEqual(step["action"], "research_prospects")
        self.assertEqual(step["output"]["attributed"], 2)
        self.assertEqual(step["output"]["skipped_known"], 1)
        # Attribution rows exist, so the run is measurable: a genuine zero
        # until a reply or meeting lands on these candidates.
        observation = execution["validation_events"]
        self.assertTrue(observation["observed"])
        self.assertEqual(observation["count"], 0)
        self.assertIsNone(observation["reason"])


if __name__ == "__main__":
    unittest.main()
