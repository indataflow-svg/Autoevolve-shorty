"""Limits are re-checked when a workflow runs, not only when it is validated.

Validation-time checks catch a plan that asks for too much. They cannot catch
the world having moved afterwards: the operator lowering a cap, the plan's time
window elapsing, or a target list larger than the volume the founder approved.
All three are questions that only exist at run time.

A refusal is preferred over truncation — a run that quietly contacts fewer
prospects looks identical to one that contacted every one of them.
"""

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import core.state as state
from app.api import app
from core import marketing_store, sales_store, workflow_store
from core.company_context import normalize_company_context, save_company_context
from core.plan_governance import latest_governance, save_governance
from core.validation_plan import (
    GroundingReport,
    PlanProvenance,
    ValidationPlan,
    WORKFLOW_TEMPLATE,
    build_plan_record,
    save_validation_plan,
)
from tests.market_validation_fixtures import NORTHLIGHT_CONTEXT, NORTHLIGHT_PLAN, plan_with


def provenance() -> PlanProvenance:
    return PlanProvenance(
        prompt_version=WORKFLOW_TEMPLATE,
        prompt_path="prompts/market_validation_v1.md",
        model_route="reasoning",
        model_name="auto/best-reasoning",
        model_provider="omniroute",
    )


class RuntimeLimitTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self._paths = (
            state.DB_PATH,
            workflow_store.DB_PATH,
            marketing_store.DB_PATH,
            sales_store.DB_PATH,
        )
        state.DB_PATH = base / "company.db"
        workflow_store.DB_PATH = base / "workflows.db"
        marketing_store.DB_PATH = sales_store.DB_PATH = base / "company.db"
        state.init_db()
        marketing_store.init_marketing_db()
        sales_store.init_sales_db()
        workflow_store.init_db()
        save_company_context(normalize_company_context(NORTHLIGHT_CONTEXT))
        self.env = patch.dict(os.environ, {
            "DASHBOARD_USER": "founder",
            "DASHBOARD_PASSWORD": "dashboard-secret",
            "SALES_ACTION_TOKEN": "action-secret",
            "SALES_SEND_RECONCILE_ON_STARTUP": "false",
        }, clear=False)
        self.env.start()
        self.client = TestClient(app)
        self.auth = ("founder", "dashboard-secret")
        self.headers = {"X-Founder-Action-Token": "action-secret"}

    def tearDown(self):
        self.env.stop()
        (
            state.DB_PATH,
            workflow_store.DB_PATH,
            marketing_store.DB_PATH,
            sales_store.DB_PATH,
        ) = self._paths
        self.temporary.cleanup()

    def store_plan(self, plan: dict) -> str:
        record = build_plan_record(
            ValidationPlan.model_validate(plan), provenance(), GroundingReport()
        )
        return save_validation_plan(record).id

    def approve(self, plan: dict) -> None:
        self.store_plan(plan)
        created = self.client.post(
            "/company/automation/governance", auth=self.auth, headers=self.headers, json={},
        )
        self.assertEqual(created.status_code, 200, created.text)
        approved = self.client.post(
            "/company/automation/governance/approve",
            auth=self.auth, headers=self.headers, json={},
        )
        self.assertEqual(approved.status_code, 200, approved.text)

    def execute(self, targets: list[str]):
        return self.client.post(
            "/company/automation/governance/run",
            auth=self.auth, headers=self.headers, json={"targets": targets},
        )

    # --- the three questions only a run can answer ---------------------------

    def test_a_run_within_the_approved_limits_executes(self):
        self.approve(plan_with(max_outreach_contacts=50, duration_days=14))
        response = self.execute(["lead_a", "lead_b"])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["lifecycle"], "executed")

    def test_more_targets_than_the_plan_approves_is_refused(self):
        self.approve(plan_with(max_outreach_contacts=2))
        response = self.execute(["lead_a", "lead_b", "lead_c"])
        self.assertEqual(response.status_code, 422, response.text)
        self.assertIn("above the approved limit of 2", response.json()["detail"])
        # Nothing ran: the workflow never left its pre-execution state.
        self.assertIsNone(latest_governance().executed_at)

    def test_a_tightened_contact_cap_still_governs_an_approved_run(self):
        self.approve(plan_with(max_outreach_contacts=50))
        with patch.dict(os.environ, {"VALIDATION_MAX_OUTREACH": "1"}, clear=False):
            response = self.execute(["lead_a", "lead_b"])
        self.assertEqual(response.status_code, 422, response.text)
        detail = response.json()["detail"]
        self.assertIn("exceeds the current governance cap", detail)
        self.assertIn("above the approved limit of 1", detail)

    def test_a_tightened_spend_cap_still_governs_an_approved_run(self):
        # Approved while the operator allowed this spend, then lowered.
        with patch.dict(os.environ, {"VALIDATION_MAX_SPEND_USD": "100"}, clear=False):
            self.approve(plan_with(max_spend_usd=100))
        with patch.dict(os.environ, {"VALIDATION_MAX_SPEND_USD": "0"}, clear=False):
            response = self.execute([])
        self.assertEqual(response.status_code, 422, response.text)
        self.assertIn("budget limit 100", response.json()["detail"])

    def test_a_tightened_duration_cap_still_governs_an_approved_run(self):
        with patch.dict(os.environ, {"VALIDATION_MAX_DURATION_DAYS": "30"}, clear=False):
            self.approve(plan_with(duration_days=30))
        with patch.dict(os.environ, {"VALIDATION_MAX_DURATION_DAYS": "7"}, clear=False):
            response = self.execute([])
        self.assertEqual(response.status_code, 422, response.text)
        self.assertIn("duration limit 30 days", response.json()["detail"])

    def test_an_elapsed_time_window_refuses_the_run(self):
        self.approve(plan_with(duration_days=14))
        record = latest_governance()
        aged = (datetime.now(timezone.utc) - timedelta(days=20)).isoformat()
        save_governance(record.model_copy(update={"approved_at": aged}))
        response = self.execute([])
        self.assertEqual(response.status_code, 422, response.text)
        detail = response.json()["detail"]
        self.assertIn("14-day window elapsed", detail)
        self.assertIn("validate it again", detail)

    def test_a_window_still_inside_its_days_allows_the_run(self):
        self.approve(plan_with(duration_days=14))
        record = latest_governance()
        recent = (datetime.now(timezone.utc) - timedelta(days=13)).isoformat()
        save_governance(record.model_copy(update={"approved_at": recent}))
        self.assertEqual(self.execute([]).status_code, 200)

    def test_every_violation_is_reported_at_once(self):
        with patch.dict(os.environ, {
            "VALIDATION_MAX_SPEND_USD": "100",
            "VALIDATION_MAX_OUTREACH": "50",
            "VALIDATION_MAX_DURATION_DAYS": "30",
        }, clear=False):
            self.approve(plan_with(max_outreach_contacts=50, max_spend_usd=100, duration_days=30))
        aged = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
        save_governance(latest_governance().model_copy(update={"approved_at": aged}))
        with patch.dict(os.environ, {
            "VALIDATION_MAX_SPEND_USD": "0",
            "VALIDATION_MAX_OUTREACH": "1",
            "VALIDATION_MAX_DURATION_DAYS": "7",
        }, clear=False):
            response = self.execute(["lead_a"])
        self.assertEqual(response.status_code, 422, response.text)
        detail = response.json()["detail"]
        self.assertIn("budget limit", detail)
        self.assertIn("outreach volume limit", detail)
        self.assertIn("duration limit", detail)
        self.assertIn("window elapsed", detail)

    # --- a refusal must be distinguishable from a successful run -------------

    def test_a_refusal_is_not_recorded_as_an_execution(self):
        self.approve(plan_with(max_outreach_contacts=1))
        self.execute(["lead_a", "lead_b"])
        record = latest_governance()
        self.assertIsNone(record.executed_at)
        self.assertIsNone(record.execution)
        workflow = workflow_store.get_workflow(record.workflow_id)
        self.assertNotEqual(workflow.state.status, "completed")


if __name__ == "__main__":
    unittest.main()
