"""Governed send: approved drafts dispatch through production; nothing else moves.

The step never approves, never invents recipients, and never fails the batch
over one bad draft. Unapproved, unknown, and over-ceiling targets are counted
aside. Dispatch itself is send_approved(), so claims, idempotency, and
reconciliation are the production path, not a workflow copy of it.
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
from core.plan_governance import normalize_method, validate_plan
from core.validation_plan import (
    GroundingReport,
    PlanProvenance,
    ValidationPlan,
    WORKFLOW_TEMPLATE,
    build_plan_record,
    save_validation_plan,
)
from core.workflow_store import GOVERNED_ACTIONS, SEND_ACTIONS
from contextlib import contextmanager
from services.workflow_actions import send_outreach
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


@contextmanager
def _dispatched(fail_ids=()):
    """Real claim/mark flow with the provider edge stubbed.

    The stub behaves like a confirming provider: it persists the sent status
    exactly as _send_resend_draft does on provider confirm. Drafts in
    fail_ids raise instead, exercising the ambiguous-outcome path.
    """
    def _send(draft, lead, *, sender=None, reply_to=None, metadata=None):
        if draft["id"] in fail_ids:
            raise ValueError("lead is unavailable or suppressed")
        sales_store.mark_sent(draft["id"], "msg-1", metadata=metadata)
        return "msg-1"

    with patch("services.sales_service._resolved_resend_sender",
               return_value="Founder <founder@example.test>"), \
            patch("services.sales_service._send_resend_draft",
                  side_effect=_send):
        yield


class SendBase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self._paths = (state.DB_PATH, commercial_store.DB_PATH, sales_store.DB_PATH,
                       workflow_store.DB_PATH, marketing_store.DB_PATH)
        state.DB_PATH = commercial_store.DB_PATH = sales_store.DB_PATH = base / "company.db"
        workflow_store.DB_PATH = base / "workflows.db"
        state.init_db()
        sales_store.init_sales_db()
        commercial_store.init_commercial_db()
        marketing_store.init_marketing_db()
        workflow_store.init_db()
        self.context = normalize_company_context(NORTHLIGHT_CONTEXT)
        save_company_context(self.context)
        self.env = patch.dict(os.environ, {
            "DASHBOARD_USER": "founder", "DASHBOARD_PASSWORD": "pw",
            "SALES_ACTION_TOKEN": "act", "SALES_SEND_RECONCILE_ON_STARTUP": "false",
        }, clear=False)
        self.env.start()
        self.client = TestClient(app)
        self.auth = ("founder", "pw")
        self.headers = {"X-Founder-Action-Token": "act"}

    def tearDown(self):
        self.env.stop()
        (state.DB_PATH, commercial_store.DB_PATH, sales_store.DB_PATH,
         workflow_store.DB_PATH, marketing_store.DB_PATH) = self._paths
        self.temporary.cleanup()

    def store_plan(self, plan: dict) -> str:
        record = build_plan_record(
            ValidationPlan.model_validate(plan), provenance(), GroundingReport())
        return save_validation_plan(record).id

    def govern(self, plan: dict):
        candidate = ValidationPlan.model_validate(plan)
        return validate_plan(candidate, self.context, plan_id=self.store_plan(plan))[0]

    def draft(self, email: str, approve: bool = False) -> str:
        lead, _ = sales_store.upsert_lead({"email": email, "source": "manual"})
        draft = sales_store.create_draft(
            lead["id"], "Following up", "A sufficiently long body for the send test.")
        if approve:
            sales_store.approve_draft(draft["id"])
        return draft["id"]


class SendActionTests(SendBase):
    def test_unapproved_drafts_are_skipped_never_sent(self):
        draft_id = self.draft("a@x.test", approve=False)
        with patch("services.sales_service._send_resend_draft",
                   side_effect=AssertionError("must not dispatch")):
            result = send_outreach({}, {"targets": [draft_id], "max_contacts": 50})
        output = result["output"]
        self.assertEqual(output["sent"], 0)
        self.assertEqual(output["skipped_unapproved"], [draft_id])
        self.assertEqual(sales_store.get_draft(draft_id)["status"], "draft")

    def test_unknown_drafts_are_skipped(self):
        result = send_outreach({}, {"targets": ["draft_nope"], "max_contacts": 50})
        self.assertEqual(result["output"]["skipped_unknown"], ["draft_nope"])
        self.assertEqual(result["output"]["sent"], 0)

    def test_approved_drafts_send_with_attribution(self):
        draft_id = self.draft("a@x.test", approve=True)
        with _dispatched():
            result = send_outreach({"plan_id": "plan_1", "workflow_id": "wf_1"},
                                   {"targets": [draft_id], "max_contacts": 50})
        output = result["output"]
        self.assertEqual(output["sent"], 1)
        self.assertEqual(output["sent_draft_ids"], [draft_id])
        self.assertIs(output["external_side_effects"], True)
        self.assertIsNone(output["validation_events"])
        stored = sales_store.get_draft(draft_id)
        self.assertEqual(stored["status"], "sent")
        self.assertEqual(stored["provider_message_id"], "msg-1")
        events = [e["event"] for e in sales_store.list_events(lead_id=stored["lead_id"])]
        self.assertIn("outreach.governed_sent", events)

    def test_ceiling_and_failures_are_counted_not_fatal(self):
        good = self.draft("a@x.test", approve=True)
        bad = self.draft("b@x.test", approve=True)
        extra = self.draft("c@x.test", approve=True)
        with _dispatched(fail_ids={bad}):
            result = send_outreach({}, {"targets": [good, bad, extra], "max_contacts": 2})
        output = result["output"]
        self.assertEqual(output["sent"], 1)
        self.assertEqual(len(output["failed"]), 1)
        self.assertEqual(output["failed"][0]["draft_id"], bad)
        self.assertEqual(output["over_ceiling"], 1)
        self.assertEqual(result["status"], "completed")

    def test_without_ceiling_nothing_sends(self):
        draft_id = self.draft("a@x.test", approve=True)
        with patch("services.sales_service._send_resend_draft",
                   side_effect=AssertionError("must not dispatch")):
            result = send_outreach({}, {"targets": [draft_id], "max_contacts": 0})
        self.assertEqual(result["output"]["sent"], 0)

    def test_send_is_governed(self):
        self.assertEqual(normalize_method("send_approved"), "approved_send")
        self.assertIn("send_outreach", GOVERNED_ACTIONS)
        self.assertIn("send_outreach", SEND_ACTIONS)


class SendGovernanceTests(SendBase):
    def send_plan(self) -> dict:
        return plan_with_validation(method="approved_send", channel="email",
                                    message="Approved copy goes out.")

    def test_approved_send_resolves_to_dispatch(self):
        decision = self.govern(self.send_plan())
        self.assertEqual(decision.status, "valid")
        (step,) = decision.resolved_actions
        self.assertEqual(step.action, "send_outreach")
        self.assertEqual(step.step_id, "send_approved_outreach")
        self.assertEqual(step.config["max_contacts"], 50)

    def test_send_run_dispatches_only_approved(self):
        good = self.draft("a@x.test", approve=True)
        waiting = self.draft("b@x.test", approve=False)
        self.store_plan(self.send_plan())
        created = self.client.post("/company/automation/governance", auth=self.auth,
                                   headers=self.headers, json={})
        self.assertEqual(created.status_code, 200, created.text)
        self.client.post("/company/automation/governance/approve", auth=self.auth,
                         headers=self.headers, json={})
        with _dispatched():
            executed = self.client.post(
                "/company/automation/governance/run", auth=self.auth, headers=self.headers,
                json={"targets": [good, waiting, "draft_nope"]})
        self.assertEqual(executed.status_code, 200, executed.text)
        step = executed.json()["execution"]["steps"][0]
        self.assertEqual(step["action"], "send_outreach")
        self.assertEqual(step["output"]["sent"], 1)
        self.assertEqual(step["output"]["skipped_unapproved"], [waiting])
        self.assertEqual(step["output"]["skipped_unknown"], ["draft_nope"])

    def test_suggester_recommends_sends_for_approved_drafts(self):
        from core.suggest import suggest_workflows
        self.draft("a@x.test", approve=True)
        self.draft("b@x.test", approve=True)
        out = suggest_workflows(0)
        rec = next(r for r in out["recommendations"] if r["method"] == "approved_send")
        self.assertEqual(rec["expected_range"]["low"], 2)
        self.assertEqual(rec["expected_range"]["unit"], "sends")
        self.assertEqual(out["evidence_summary"]["approved_unsent"], 2)


if __name__ == "__main__":
    unittest.main()
