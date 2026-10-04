"""Governance: a Hermes plan becomes a runnable workflow, or is blocked.

Governance is deterministic and side-effect free, so these tests exercise the real
workflow store and the real runner. The only action governance may authorize is
``simulate_outreach``; the tests assert that no lead, campaign, task, or provider
call results from the whole path.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import core.state as state
from app.api import app
from core import marketing_store, sales_store, workflow_store
from core.company_context import normalize_company_context, save_company_context
from core.plan_governance import (
    GovernanceLimits,
    latest_governance,
    normalize_channel,
    normalize_method,
    record_from_decision,
    save_governance,
    validate_plan,
)
from core.validation_plan import (
    GroundingReport,
    PlanProvenance,
    ValidationPlan,
    WORKFLOW_TEMPLATE,
    build_plan_record,
    save_validation_plan,
)
from core.workflow_store import SIMULATION_ACTIONS, WORKFLOW_ACTIONS
from services import workflow_runner
from tests.market_validation_fixtures import (
    MOCK_PROSPECTS,
    NORTHLIGHT_CONTEXT,
    NORTHLIGHT_PLAN,
    plan_with,
    plan_with_validation,
)

MOCK_TARGETS = [prospect["id"] for prospect in MOCK_PROSPECTS]


def provenance() -> PlanProvenance:
    return PlanProvenance(
        prompt_version=WORKFLOW_TEMPLATE, prompt_path="prompts/market_validation_v1.md",
        model_route="reasoning", model_name="auto/best-reasoning", model_provider="omniroute",
    )


class GovernanceBase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self._paths = (state.DB_PATH, workflow_store.DB_PATH, marketing_store.DB_PATH, sales_store.DB_PATH)
        state.DB_PATH = self.base / "company.db"
        workflow_store.DB_PATH = self.base / "workflows.db"
        marketing_store.DB_PATH = sales_store.DB_PATH = self.base / "company.db"
        state.init_db()
        marketing_store.init_marketing_db()
        sales_store.init_sales_db()
        workflow_store.init_db()
        self.context = normalize_company_context(NORTHLIGHT_CONTEXT)
        save_company_context(self.context)

    def tearDown(self):
        state.DB_PATH, workflow_store.DB_PATH, marketing_store.DB_PATH, sales_store.DB_PATH = self._paths
        self.temporary.cleanup()

    def store_plan(self, plan: dict | None = None) -> str:
        record = build_plan_record(
            ValidationPlan.model_validate(plan or NORTHLIGHT_PLAN), provenance(), GroundingReport(),
        )
        return save_validation_plan(record).id

    def govern(self, plan: dict | None = None, **kwargs):
        candidate = ValidationPlan.model_validate(plan or NORTHLIGHT_PLAN)
        return validate_plan(candidate, self.context, plan_id=self.store_plan(plan) if plan else "", **kwargs)


class PlanValidatorTests(GovernanceBase):
    """The deterministic checks, one at a time."""

    def test_valid_plan_passes_with_a_resolved_simulation_action(self):
        decision, plan = self.govern()
        self.assertEqual(decision.status, "valid", decision.reasons)
        self.assertEqual(decision.reasons, [])
        self.assertTrue(decision.required_approval)
        self.assertEqual(len(decision.resolved_actions), 1)
        action = decision.resolved_actions[0]
        self.assertEqual(action.action, "simulate_outreach")
        self.assertIn(action.action, SIMULATION_ACTIONS)
        self.assertEqual(action.config["channel"], "email")
        self.assertEqual(action.config["max_contacts"], 50)
        self.assertEqual(action.config["duration_days"], 14)
        self.assertEqual(plan.workflow_template, WORKFLOW_TEMPLATE)

    def test_unsupported_method_is_blocked(self):
        for method in ("landing_page_test", "organic_content", "paid_acquisition", "cold email"):
            decision, _ = self.govern(plan_with_validation(method=method))
            self.assertEqual(decision.status, "blocked", method)
            self.assertTrue(any("no governed workflow action" in reason for reason in decision.reasons), decision.reasons)
            self.assertEqual(decision.resolved_actions, [])

    def test_unsupported_or_unconfirmed_channel_is_blocked(self):
        unsupported, _ = self.govern(plan_with_validation(channel="carrier pigeon"))
        self.assertEqual(unsupported.status, "blocked")
        self.assertTrue(any("not a supported validation channel" in reason for reason in unsupported.reasons))

        unconfirmed, _ = self.govern(plan_with_validation(channel="whatsapp"))
        self.assertEqual(unconfirmed.status, "blocked")
        self.assertTrue(any("not among the founder-confirmed channels" in reason for reason in unconfirmed.reasons))

        confirmed, _ = self.govern(plan_with_validation(channel="LinkedIn"))
        self.assertEqual(confirmed.status, "valid", confirmed.reasons)
        self.assertEqual(confirmed.resolved_actions[0].config["channel"], "linkedin")

    def test_budget_volume_and_duration_limits_block_over_limit_plans(self):
        cases = {
            "budget limit": plan_with(max_spend_usd=250),
            "outreach volume limit": plan_with(max_outreach_contacts=500),
            "duration limit": plan_with(duration_days=90),
        }
        for expected, plan in cases.items():
            decision, _ = self.govern(plan)
            self.assertEqual(decision.status, "blocked", plan)
            self.assertTrue(any(expected in reason for reason in decision.reasons), decision.reasons)
            self.assertEqual(decision.resolved_actions, [])

    def test_limits_default_to_zero_spend_and_load_from_the_environment(self):
        self.assertEqual(GovernanceLimits.load().max_spend_usd, 0.0)
        with patch.dict("os.environ", {"VALIDATION_MAX_SPEND_USD": "500", "VALIDATION_MAX_OUTREACH": "120"}):
            limits = GovernanceLimits.load()
        self.assertEqual(limits.max_spend_usd, 500.0)
        self.assertEqual(limits.max_outreach_contacts, 120)
        decision, _ = self.govern(plan_with(max_spend_usd=250), limits=limits)
        self.assertEqual(decision.status, "valid", decision.reasons)

    def test_missing_experiment_content_is_blocked(self):
        without_validation = {key: value for key, value in NORTHLIGHT_PLAN.items() if key != "validation"}
        decision, _ = validate_plan(without_validation, self.context, plan_id="plan_x")
        self.assertEqual(decision.status, "blocked")
        self.assertTrue(any("not a valid validation plan" in reason for reason in decision.reasons))
        self.assertEqual(decision.resolved_actions, [])

        blank_message, _ = validate_plan(plan_with_validation(message=" "), self.context, plan_id="plan_y")
        self.assertEqual(blank_message.status, "blocked")
        self.assertEqual(blank_message.resolved_actions, [])

    def test_untraceable_fact_is_demoted_and_reported_but_still_governable(self):
        plan = {
            **NORTHLIGHT_PLAN,
            "evidence": {
                **NORTHLIGHT_PLAN["evidence"],
                "known_facts": ["Two paid setups", "We won the 2025 logistics innovation award"],
            },
        }
        decision, grounded = self.govern(plan)
        self.assertEqual(grounded.evidence.known_facts, ["Two paid setups"])
        self.assertIn("We won the 2025 logistics innovation award", grounded.evidence.assumptions)
        self.assertEqual(decision.status, "valid", decision.reasons)
        self.assertTrue(any("moved to assumptions" in warning for warning in decision.warnings))
        self.assertEqual(decision.grounding.checked_facts, 2)

    def test_structurally_invalid_plan_is_blocked_with_the_reason(self):
        decision, _ = validate_plan({"workflow_template": "market_validation_v1"}, self.context, plan_id="plan_x")
        self.assertEqual(decision.status, "blocked")
        self.assertTrue(any("not a valid validation plan" in reason for reason in decision.reasons))
        self.assertEqual(decision.resolved_actions, [])

    def test_declared_constraints_require_approval_and_are_reported(self):
        decision, _ = self.govern()
        self.assertTrue(decision.required_approval)
        self.assertTrue(any("declared company constraints" in warning for warning in decision.warnings))
        self.assertTrue(any("United States only for the first year" in warning for warning in decision.warnings))

    def test_a_plan_cannot_waive_approval(self):
        decision, _ = self.govern(plan_with(requires_approval=False))
        self.assertTrue(decision.required_approval)
        self.assertTrue(any("still requires founder approval" in warning for warning in decision.warnings))

    def test_governance_never_authorizes_a_real_external_action(self):
        # The only registered actions that reach real systems must stay unreachable.
        for action in ("g1_strategy", "generate_assets", "publish"):
            self.assertIn(action, WORKFLOW_ACTIONS)
            self.assertNotIn(action, SIMULATION_ACTIONS)

    def test_channel_and_method_wording_is_normalized(self):
        self.assertEqual(normalize_channel("E-Mail"), "email")
        self.assertEqual(normalize_channel("landing page test"), "landing-page")
        self.assertEqual(normalize_method("Targeted Outbound"), "targeted_outbound")
        self.assertEqual(normalize_method("cold outreach"), "targeted_outbound")


class MockExecutionTests(GovernanceBase):
    """The full path: plan -> governance -> workflow -> runner -> simulation."""

    def _governed_workflow(self):
        from app import validation_api

        self.client = TestClient(app)
        self.auth = ("founder", "dashboard-secret")
        self.headers = {"X-Founder-Action-Token": "action-secret"}
        self.store_plan()
        decision, _ = validate_plan(ValidationPlan.model_validate(NORTHLIGHT_PLAN), self.context, plan_id="")
        save_governance(record_from_decision(decision))
        created = self.client.post(
            "/company/marketing/validation/workflow", auth=self.auth, headers=self.headers, json={},
        )
        self.assertEqual(created.status_code, 200, created.text)
        self.assertEqual(created.json()["status"], "valid")
        return created.json()

    def setUp(self):
        super().setUp()
        import os
        self.env = patch.dict(os.environ, {
            "DASHBOARD_USER": "founder", "DASHBOARD_PASSWORD": "dashboard-secret",
            "SALES_ACTION_TOKEN": "action-secret", "SALES_SEND_RECONCILE_ON_STARTUP": "false",
        }, clear=False)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        super().tearDown()

    def test_plan_to_workflow_to_simulated_result(self):
        record = self._governed_workflow()
        self.assertEqual(record["lifecycle"], "workflow_created")
        workflow = workflow_store.get_workflow(record["workflow_id"])
        self.assertIsNotNone(workflow)
        self.assertEqual(workflow.state.status, "draft")  # created, not executed
        self.assertEqual(workflow.trigger.config["simulation"], True)
        self.assertEqual(workflow.trigger.config["plan_id"], get_latest_plan_id())
        self.assertEqual([step["action"] for step in workflow.model_dump()["steps"]], ["simulate_outreach"])
        self.assertEqual(workflow.success_metric.target, 5.0)

        # Governance requires approval: the runner is not reachable yet.
        blocked_run = self.client.post(
            "/company/marketing/validation/workflow/run", auth=self.auth,
            headers=self.headers, json={"targets": MOCK_TARGETS},
        )
        self.assertEqual(blocked_run.status_code, 409)
        self.assertIn("approval", blocked_run.json()["detail"])
        self.assertEqual(workflow_store.get_workflow(record["workflow_id"]).state.status, "draft")

        approved = self.client.post(
            "/company/marketing/validation/workflow/approve", auth=self.auth, headers=self.headers, json={},
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json()["lifecycle"], "approved")
        self.assertEqual(workflow_store.get_workflow(record["workflow_id"]).state.status, "ready")

        executed = self.client.post(
            "/company/marketing/validation/workflow/run", auth=self.auth,
            headers=self.headers, json={"targets": MOCK_TARGETS},
        )
        self.assertEqual(executed.status_code, 200, executed.text)
        body = executed.json()
        self.assertEqual(body["lifecycle"], "executed")
        self.assertEqual(body["execution"]["status"], "completed")
        self.assertEqual(len(body["execution"]["steps"]), 1)

        simulated = body["execution"]["steps"][0]["output"]
        self.assertEqual(simulated["status"], "simulated")
        self.assertEqual(simulated["action"], "outreach")
        self.assertEqual(simulated["targets"], 3)
        self.assertEqual(simulated["sent"], 3)
        self.assertEqual(simulated["replies"], 0)
        self.assertIs(simulated["external_side_effects"], False)
        self.assertEqual(
            [item["prospect_id"] for item in simulated["results"]], MOCK_TARGETS,
        )

        # The lifecycle is observable and survives a reload.
        state_record = self.client.get("/company/marketing/validation/workflow", auth=self.auth).json()
        self.assertEqual(state_record["lifecycle"], "executed")
        self.assertEqual(latest_governance().workflow_id, record["workflow_id"])

    def test_simulation_has_no_external_side_effects(self):
        self._governed_workflow()
        self.client.post("/company/marketing/validation/workflow/approve", auth=self.auth, headers=self.headers, json={})
        with patch("services.marketing_worker.run_g1") as g1, \
             patch("services.marketing_worker.run_media_pipeline") as g2, \
             patch("services.marketing_worker.run_g3") as g3, \
             patch("services.workflow_actions.apollo_client", create=True) as apollo:
            response = self.client.post(
                "/company/marketing/validation/workflow/run", auth=self.auth,
                headers=self.headers, json={"targets": MOCK_TARGETS},
            )
        self.assertEqual(response.status_code, 200, response.text)
        for engine in (g1, g2, g3, apollo):
            engine.assert_not_called()
        # No sales lead, no campaign, no task was created by the simulation.
        self.assertEqual(sales_store.summary()["total"], 0)
        with marketing_store.connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM marketing_campaigns").fetchone()[0], 0)
        self.assertEqual(state.get_recent_tasks(limit=10), [])

    def test_blocked_plan_creates_no_workflow_and_cannot_run(self):
        self.client = TestClient(app)
        self.auth = ("founder", "dashboard-secret")
        self.headers = {"X-Founder-Action-Token": "action-secret"}
        self.store_plan(plan_with(max_spend_usd=5000))
        created = self.client.post(
            "/company/marketing/validation/workflow", auth=self.auth, headers=self.headers, json={},
        )
        self.assertEqual(created.status_code, 200, created.text)
        body = created.json()
        self.assertEqual(body["status"], "blocked")
        self.assertEqual(body["lifecycle"], "blocked")
        self.assertIsNone(body["workflow_id"])
        self.assertTrue(any("budget limit" in reason for reason in body["reasons"]))
        self.assertEqual(workflow_store.list_workflows(), [])

        run = self.client.post(
            "/company/marketing/validation/workflow/run", auth=self.auth, headers=self.headers, json={},
        )
        self.assertEqual(run.status_code, 409)
        self.assertIn("blocked by governance", run.json()["detail"])
        self.assertEqual(workflow_store.list_workflows(), [])

    def test_execution_requires_the_founder_token_and_a_stored_plan(self):
        self.client = TestClient(app)
        self.auth = ("founder", "dashboard-secret")
        self.headers = {"X-Founder-Action-Token": "action-secret"}
        self.assertEqual(
            self.client.get("/company/marketing/validation/workflow", auth=self.auth).status_code, 404
        )
        self.assertEqual(
            self.client.post("/company/marketing/validation/workflow", auth=self.auth).status_code, 403
        )
        self.assertEqual(
            self.client.post("/company/marketing/validation/workflow/run", auth=self.auth).status_code, 403
        )
        self.assertEqual(
            self.client.get("/company/marketing/validation/workflow").status_code, 401
        )

    def test_runner_validates_the_created_workflow_and_the_action_is_deterministic(self):
        self._governed_workflow()
        workflow = workflow_store.get_workflow(latest_governance().workflow_id)
        self.assertEqual(workflow_runner.validate_workflow(workflow), [])
        first = workflow_actions_output(workflow)
        second = workflow_actions_output(workflow)
        self.assertEqual(first, second)
        self.assertEqual(first["external_side_effects"], False)


def workflow_actions_output(workflow) -> dict:
    from services.workflow_actions import simulate_outreach

    step = workflow.steps[0]
    config = {**step.config, "targets": MOCK_TARGETS}
    return simulate_outreach({}, config)["output"]


def get_latest_plan_id() -> str:
    from core.validation_plan import get_latest_validation_plan

    record = get_latest_validation_plan()
    return record.id if record else ""


if __name__ == "__main__":
    unittest.main()