"""Validation events are observed, never assumed.

Three different situations all look like zero on a dashboard unless they are
kept apart:

- a run nobody measured,
- an evidence store that could not be read,
- a genuine "we looked and there were none".

Only the last is a zero. The first is absence of evidence and must not render
as a failed experiment — the same rule the QA gate applies to ``SKIPPED``, and
the same reason a provider outage is never reported as an empty search.
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
from core.validation_plan import (
    GroundingReport,
    PlanProvenance,
    ValidationPlan,
    WORKFLOW_TEMPLATE,
    build_plan_record,
    save_validation_plan,
)
from services.workflow_actions import observe_validation_events, simulate_outreach
from tests.market_validation_fixtures import (
    MOCK_PROSPECTS,
    NORTHLIGHT_CONTEXT,
    NORTHLIGHT_PLAN,
)

MOCK_TARGETS = [prospect["id"] for prospect in MOCK_PROSPECTS]


def provenance() -> PlanProvenance:
    return PlanProvenance(
        prompt_version=WORKFLOW_TEMPLATE,
        prompt_path="prompts/market_validation_v1.md",
        model_route="reasoning",
        model_name="auto/best-reasoning",
        model_provider="omniroute",
    )


class ObservationBase(unittest.TestCase):
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

    def tearDown(self):
        (
            state.DB_PATH,
            workflow_store.DB_PATH,
            marketing_store.DB_PATH,
            sales_store.DB_PATH,
        ) = self._paths
        self.temporary.cleanup()

    def store_plan(self) -> str:
        record = build_plan_record(
            ValidationPlan.model_validate(NORTHLIGHT_PLAN), provenance(), GroundingReport()
        )
        return save_validation_plan(record).id


class SimulationTests(ObservationBase):
    """The simulated step must not claim to have measured anything."""

    def test_simulation_reports_no_count_in_output_or_metrics(self):
        result = simulate_outreach({}, {"targets": MOCK_TARGETS, "channel": "linkedin"})
        self.assertIsNone(result["output"]["validation_events"])
        self.assertNotIn("validation_events", result["metrics"])
        # Nothing else about the simulation changes: it still reaches nothing.
        self.assertIs(result["output"]["external_side_effects"], False)
        self.assertEqual(result["output"]["status"], "simulated")


class ObservationTests(ObservationBase):
    """What counts as evidence, and what does not."""

    def test_without_identifiers_there_is_nothing_to_measure(self):
        observation = observe_validation_events()
        self.assertFalse(observation.observed)
        self.assertEqual(observation.count, 0)
        self.assertIsNone(observation.source)
        self.assertTrue(observation.reason)

    def test_no_attributed_activity_is_absence_of_evidence_not_a_zero(self):
        observation = observe_validation_events(plan_id="plan_does_not_exist")
        self.assertFalse(observation.observed)
        self.assertEqual(observation.count, 0)
        self.assertEqual(observation.source, "sales_events(plan_id=plan_does_not_exist)")
        self.assertIn("no outreach has been recorded", observation.reason)

    def test_unattributed_events_are_not_credited_to_this_plan(self):
        # Real leads sitting in a meeting stage were not produced by this
        # experiment, so counting them would credit a run that never happened.
        sales_store.add_event("lead_unrelated", "meeting.scheduled", {"when": "soon"})
        sales_store.add_event("lead_unrelated", "lead.replied", {"subject": "hi"})
        observation = observe_validation_events(plan_id="plan_abc123")
        self.assertFalse(observation.observed)
        self.assertEqual(observation.count, 0)

    def test_attributed_validation_events_are_counted(self):
        plan_id = "plan_abc123"
        for event in ("outreach.sent", "lead.replied", "meeting.scheduled"):
            sales_store.add_event("lead_one", event, {"plan_id": plan_id})
        observation = observe_validation_events(plan_id=plan_id)
        self.assertTrue(observation.observed)
        # Outreach activity is not itself a validation event.
        self.assertEqual(observation.count, 2)
        self.assertIsNone(observation.reason)

    def test_attributed_activity_with_no_event_is_a_genuine_zero(self):
        plan_id = "plan_zero_case"
        sales_store.add_event("lead_one", "outreach.sent", {"plan_id": plan_id})
        observation = observe_validation_events(plan_id=plan_id)
        self.assertTrue(observation.observed)
        self.assertEqual(observation.count, 0)
        self.assertIsNone(observation.reason)

    def test_workflow_id_also_attributes_evidence(self):
        sales_store.add_event("lead_one", "lead.replied", {"workflow_id": "wf_seen1"})
        observation = observe_validation_events(workflow_id="wf_seen1")
        self.assertTrue(observation.observed)
        self.assertEqual(observation.count, 1)


class RunAttachesObservationTests(ObservationBase):
    """The executed governance record carries an observation, not a number."""

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

    def test_run_reports_no_score_until_evidence_exists(self):
        plan_id = self.store_plan()
        created = self.client.post(
            "/company/automation/governance", auth=self.auth, headers=self.headers, json={},
        )
        self.assertEqual(created.status_code, 200, created.text)
        approved = self.client.post(
            "/company/automation/governance/approve",
            auth=self.auth, headers=self.headers, json={},
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        executed = self.client.post(
            "/company/automation/governance/run",
            auth=self.auth, headers=self.headers, json={"targets": MOCK_TARGETS},
        )
        self.assertEqual(executed.status_code, 200, executed.text)
        execution = executed.json()["execution"]

        observation = execution["validation_events"]
        self.assertFalse(observation["observed"])
        self.assertEqual(observation["count"], 0)
        self.assertTrue(observation["reason"])
        # The plan is attached, so the evidence store was genuinely consulted.
        self.assertIn(plan_id, observation["source"])

        # The simulated step itself reports no count at all.
        step_output = execution["steps"][0]["output"]
        self.assertIsNone(step_output["validation_events"])
        self.assertIs(step_output["external_side_effects"], False)

    def test_observation_flips_once_attributable_evidence_exists(self):
        plan_id = self.store_plan()
        created = self.client.post(
            "/company/automation/governance", auth=self.auth, headers=self.headers, json={},
        )
        self.assertEqual(created.status_code, 200, created.text)
        workflow_id = created.json()["workflow_id"]
        self.client.post(
            "/company/automation/governance/approve",
            auth=self.auth, headers=self.headers, json={},
        )
        sales_store.add_event("lead_one", "meeting.scheduled", {
            "plan_id": plan_id, "workflow_id": workflow_id,
        })
        executed = self.client.post(
            "/company/automation/governance/run",
            auth=self.auth, headers=self.headers, json={"targets": MOCK_TARGETS},
        )
        self.assertEqual(executed.status_code, 200, executed.text)
        observation = executed.json()["execution"]["validation_events"]
        self.assertTrue(observation["observed"])
        self.assertEqual(observation["count"], 1)


if __name__ == "__main__":
    unittest.main()
