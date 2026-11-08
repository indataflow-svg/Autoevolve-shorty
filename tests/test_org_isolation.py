"""Tenant isolation: context, plans, and workflows stay inside one org."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core import commercial_store, sales_store, state, workflow_store
from core.company_context import (
    get_company_context,
    normalize_company_context,
    save_company_context,
)
from core.validation_plan import (
    GroundingReport,
    PlanProvenance,
    ValidationPlan,
    build_plan_record,
    get_latest_validation_plan,
    save_validation_plan,
)
from tests.market_validation_fixtures import NORTHLIGHT_CONTEXT, NORTHLIGHT_PLAN


class OrgIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.old = (
            state.DB_PATH,
            commercial_store.DB_PATH,
            sales_store.DB_PATH,
            workflow_store.DB_PATH,
        )
        state.DB_PATH = commercial_store.DB_PATH = sales_store.DB_PATH = root / "company.db"
        workflow_store.DB_PATH = root / "workflows.db"
        state.init_db()
        sales_store.init_sales_db()
        commercial_store.init_commercial_db()
        workflow_store.init_db()
        self.a = state.create_org("Org A", "org-a")
        self.b = state.create_org("Org B", "org-b")
        state.set_active_org(self.a["id"])
        save_company_context(normalize_company_context(NORTHLIGHT_CONTEXT), self.a["id"])

    def tearDown(self):
        state.DB_PATH, commercial_store.DB_PATH, sales_store.DB_PATH, workflow_store.DB_PATH = self.old
        self.temp.cleanup()

    def _plan(self, org_id: int, plan_id: str):
        plan = ValidationPlan.model_validate(NORTHLIGHT_PLAN)
        provenance = PlanProvenance(
            prompt_version="market_validation_v1",
            prompt_path="prompts/market_validation_v1.md",
            model_route="reasoning",
            model_name="fixture",
            model_provider="fixture",
        )
        return save_validation_plan(
            build_plan_record(plan, provenance, GroundingReport(), org_id=org_id)
        )

    def test_context_is_isolated(self):
        self.assertIsNotNone(get_company_context(self.a["id"]))
        self.assertIsNone(get_company_context(self.b["id"]))

    def test_plans_are_isolated(self):
        self._plan(self.a["id"], "plan-a")
        self._plan(self.b["id"], "plan-b")
        self.assertEqual(get_latest_validation_plan(self.a["id"]).org_id, self.a["id"])
        self.assertEqual(get_latest_validation_plan(self.b["id"]).org_id, self.b["id"])
        self.assertNotEqual(
            get_latest_validation_plan(self.a["id"]).id,
            get_latest_validation_plan(self.b["id"]).id,
        )

    def test_workflows_are_isolated(self):
        wa = workflow_store.create_workflow(name="A workflow", org_id=self.a["id"])
        wb = workflow_store.create_workflow(name="B workflow", org_id=self.b["id"])
        self.assertEqual([w.id for w in workflow_store.list_workflows(org_id=self.a["id"])], [wa.id])
        self.assertEqual([w.id for w in workflow_store.list_workflows(org_id=self.b["id"])], [wb.id])
        self.assertEqual(workflow_store.get_workflow(wa.id).org_id, self.a["id"])


if __name__ == "__main__":
    unittest.main()
