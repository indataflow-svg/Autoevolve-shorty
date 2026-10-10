"""A governed workflow can leave a real artifact without sending anything.

Drafting is the middle state between simulating and sending: a draft is a real
record the founder reviews and sends by hand, so the step itself cannot contact
anyone. Its purpose is to make the experiment attributable — once the plan's id
is attached to the events, later evidence belongs to this run rather than to
whatever else is in the lead store.

Two invariants are guarded here: drafting never sends, and an action that is
registered but not authorized by governance stays unreachable even though the
runner could execute it.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import core.state as state
from app.api import app
from core import marketing_store, sales_store, workflow_store
from core.company_context import normalize_company_context, save_company_context
from core.plan_governance import validate_plan
from core.validation_plan import (
    GroundingReport,
    PlanProvenance,
    ValidationPlan,
    WORKFLOW_TEMPLATE,
    build_plan_record,
    save_validation_plan,
)
from core.workflow_store import EXTERNAL_ACTIONS, GOVERNED_ACTIONS, WORKFLOW_ACTIONS
from services.workflow_actions import draft_outreach, observe_validation_events
from tests.market_validation_fixtures import (
    NORTHLIGHT_CONTEXT,
    NORTHLIGHT_PLAN,
    plan_with_validation,
)

DRAFT_MESSAGE = "Your dispatch handoffs run on spreadsheets. Worth comparing notes?"


def provenance() -> PlanProvenance:
    return PlanProvenance(
        prompt_version=WORKFLOW_TEMPLATE,
        prompt_path="prompts/market_validation_v1.md",
        model_route="reasoning",
        model_name="auto/best-reasoning",
        model_provider="omniroute",
    )


class DraftBase(unittest.TestCase):
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
        self.context = normalize_company_context(NORTHLIGHT_CONTEXT)
        save_company_context(self.context)

    def tearDown(self):
        (
            state.DB_PATH,
            workflow_store.DB_PATH,
            marketing_store.DB_PATH,
            sales_store.DB_PATH,
        ) = self._paths
        self.temporary.cleanup()

    def store_plan(self, plan: dict | None = None) -> str:
        record = build_plan_record(
            ValidationPlan.model_validate(plan or NORTHLIGHT_PLAN),
            provenance(),
            GroundingReport(),
        )
        return save_validation_plan(record).id

    def govern(self, plan: dict):
        candidate = ValidationPlan.model_validate(plan)
        return validate_plan(candidate, self.context, plan_id=self.store_plan(plan))[0]

    def lead(self, email: str) -> str:
        created, _ = sales_store.upsert_lead({"email": email, "source": "manual"})
        return created["id"]


class DraftGovernanceTests(DraftBase):
    """Which methods resolve onto which actions — and which are refused."""

    def draft_plan(self, **overrides) -> dict:
        base = {"method": "email_outreach", "channel": "email", "message": DRAFT_MESSAGE}
        base.update(overrides)
        return plan_with_validation(**base)

    def test_email_outreach_resolves_to_drafting(self):
        decision = self.govern(self.draft_plan())
        self.assertEqual(decision.status, "valid")
        self.assertEqual([item.action for item in decision.resolved_actions], ["draft_outreach"])

    def test_targeted_outbound_still_resolves_to_simulation(self):
        decision = self.govern(plan_with_validation(method="targeted_outbound"))
        self.assertEqual(decision.status, "valid")
        self.assertEqual([item.action for item in decision.resolved_actions], ["simulate_outreach"])

    def test_a_registered_action_governance_does_not_authorize_is_refused(self):
        # The runner could execute g1_strategy; a validation plan must not reach it.
        self.assertIn("g1_strategy", WORKFLOW_ACTIONS)
        self.assertNotIn("g1_strategy", GOVERNED_ACTIONS)
        with patch.dict("core.plan_governance.METHOD_ACTIONS", {"side_venture": ("g1_strategy", "x")}):
            decision = self.govern(self.draft_plan(method="side_venture"))
        self.assertEqual(decision.status, "blocked")
        self.assertTrue(
            any("not authorized by governance" in reason for reason in decision.reasons),
            decision.reasons,
        )

    def test_an_external_action_is_refused_with_the_stricter_reason(self):
        with patch("core.plan_governance.EXTERNAL_ACTIONS", ("draft_outreach",)):
            decision = self.govern(self.draft_plan())
        self.assertEqual(decision.status, "blocked")
        self.assertTrue(
            any("reaches a real external system" in reason for reason in decision.reasons),
            decision.reasons,
        )

    def test_the_external_action_list_is_still_empty(self):
        # Sending is not reachable until limits are enforced at run time.
        self.assertEqual(EXTERNAL_ACTIONS, ())


class DraftOutreachActionTests(DraftBase):
    """The action itself: real drafts, no sends, attributed events."""

    def config(self, targets, **extra) -> dict:
        config = {
            "channel": "email",
            "message": DRAFT_MESSAGE,
            "call_to_action": "Book a discovery call",
            "offer": "A guided setup",
            "max_contacts": 50,
            "targets": list(targets),
        }
        config.update(extra)
        return config

    def test_known_targets_become_drafts(self):
        lead_id = self.lead("ops@north.test")
        result = draft_outreach({"plan_id": "plan_1", "workflow_id": "wf_1"},
                                self.config([lead_id]))
        self.assertEqual(result["output"]["drafts_created"], 1)
        self.assertEqual(result["output"]["sent"], 0)
        self.assertEqual(result["output"]["targets"], 1)
        with sales_store.connect() as connection:
            rows = connection.execute("SELECT * FROM sales_drafts").fetchall()
        drafts = [dict(row) for row in rows]
        self.assertEqual(len(drafts), 1)
        self.assertEqual(drafts[0]["lead_id"], lead_id)
        self.assertEqual(drafts[0]["subject"], "Book a discovery call")
        self.assertEqual(drafts[0]["body"], DRAFT_MESSAGE)

    def test_unknown_targets_are_skipped_not_invented(self):
        lead_id = self.lead("ops@north.test")
        result = draft_outreach(
            {"plan_id": "plan_1", "workflow_id": "wf_1"},
            self.config([lead_id, "lead_does_not_exist"]),
        )
        output = result["output"]
        self.assertEqual(output["drafts_created"], 1)
        self.assertEqual(output["skipped"], ["lead_does_not_exist"])
        self.assertEqual(output["within_limit"], 2)

    def test_drafting_never_sends(self):
        lead_id = self.lead("ops@north.test")
        result = draft_outreach({"plan_id": "plan_1", "workflow_id": "wf_1"},
                                self.config([lead_id]))
        output = result["output"]
        self.assertIs(output["external_side_effects"], False)
        self.assertEqual(output["sent"], 0)
        self.assertEqual(output["replies"], 0)
        self.assertIsNone(output["validation_events"])
        self.assertIsNone(result["metrics"].get("validation_events"))
        # Nothing reaches the provider send path: every draft stays unsent.
        with sales_store.connect() as connection:
            rows = connection.execute(
                "SELECT provider_message_id FROM sales_drafts"
            ).fetchall()
        self.assertEqual([row["provider_message_id"] for row in rows], [None])

    def test_attribution_carries_the_plan_and_workflow(self):
        lead_id = self.lead("ops@north.test")
        draft_outreach({"plan_id": "plan_abc", "workflow_id": "wf_xyz"},
                       self.config([lead_id]))
        with sales_store.connect() as connection:
            rows = connection.execute(
                "SELECT event, payload_json FROM sales_events"
            ).fetchall()
        events = {row["event"]: row["payload_json"] for row in rows}
        self.assertIn("outreach.plan_attributed", events)
        self.assertIn("plan_abc", events["outreach.plan_attributed"])
        self.assertIn("wf_xyz", events["outreach.plan_attributed"])

    def test_attribution_is_what_makes_the_run_measurable(self):
        lead_id = self.lead("ops@north.test")
        unobserved = observe_validation_events(plan_id="plan_abc")
        self.assertFalse(unobserved.observed)

        draft_outreach({"plan_id": "plan_abc", "workflow_id": "wf_xyz"},
                       self.config([lead_id]))
        observed = observe_validation_events(plan_id="plan_abc")
        self.assertTrue(observed.observed)
        # Drafts are activity, not outcomes: a real, reportable zero.
        self.assertEqual(observed.count, 0)

    def test_the_contact_ceiling_is_hard(self):
        leads = [self.lead(f"a{n}@north.test") for n in range(3)]
        result = draft_outreach(
            {"plan_id": "plan_1", "workflow_id": "wf_1"},
            self.config(leads, max_contacts=1),
        )
        self.assertEqual(result["output"]["within_limit"], 1)
        self.assertEqual(result["output"]["drafts_created"], 1)

    def test_without_a_ceiling_it_drafts_nothing(self):
        lead_id = self.lead("ops@north.test")
        result = draft_outreach(
            {"plan_id": "plan_1", "workflow_id": "wf_1"},
            self.config([lead_id], max_contacts=0),
        )
        self.assertEqual(result["output"]["drafts_created"], 0)

    def test_a_plan_without_a_message_is_refused(self):
        with self.assertRaises(ValueError):
            draft_outreach({}, self.config([], message="   "))


class DraftRunTests(DraftBase):
    """End to end: govern, approve, run, and the score becomes real."""

    def setUp(self):
        super().setUp()
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
        super().tearDown()

    def test_a_drafting_run_leaves_artifacts_and_a_measured_zero(self):
        leads = [self.lead(f"ops{n}@north.test") for n in range(2)]
        plan_id = self.store_plan(plan_with_validation(
            method="email_outreach", channel="email", message=DRAFT_MESSAGE,
        ))
        created = self.client.post(
            "/company/automation/governance", auth=self.auth, headers=self.headers, json={},
        )
        self.assertEqual(created.status_code, 200, created.text)
        workflow_id = created.json()["workflow_id"]
        workflow = workflow_store.get_workflow(workflow_id)
        self.assertEqual([step.action for step in workflow.steps], ["draft_outreach"])

        approved = self.client.post(
            "/company/automation/governance/approve",
            auth=self.auth, headers=self.headers, json={},
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(workflow_store.get_workflow(workflow_id).state.status, "ready")

        executed = self.client.post(
            "/company/automation/governance/run", auth=self.auth,
            headers=self.headers, json={"targets": [*leads, "lead_typo"]},
        )
        self.assertEqual(executed.status_code, 200, executed.text)
        execution = executed.json()["execution"]
        self.assertEqual(execution["status"], "completed")

        step = execution["steps"][0]
        self.assertEqual(step["action"], "draft_outreach")
        self.assertEqual(step["output"]["drafts_created"], 2)
        self.assertEqual(step["output"]["sent"], 0)
        self.assertEqual(step["output"]["skipped"], ["lead_typo"])
        self.assertIs(step["output"]["external_side_effects"], False)

        # The artifact exists, nothing was sent, and the run is now measurable.
        with sales_store.connect() as connection:
            sent = connection.execute(
                "SELECT COUNT(*) FROM sales_drafts WHERE provider_message_id IS NOT NULL"
            ).fetchone()[0]
        self.assertEqual(sent, 0)
        observation = execution["validation_events"]
        self.assertTrue(observation["observed"])
        self.assertEqual(observation["count"], 0)
        self.assertIn(plan_id, observation["source"])

        # Evidence added afterwards is attributed to this run.
        sales_store.add_event(leads[0], "meeting.scheduled", {"plan_id": plan_id})
        later = observe_validation_events(plan_id=plan_id)
        self.assertTrue(later.observed)
        self.assertEqual(later.count, 1)


if __name__ == "__main__":
    unittest.main()
