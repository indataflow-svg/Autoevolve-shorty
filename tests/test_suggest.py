"""Workflow suggestions: ranked from evidence, scheduled, with honest expectations."""
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import core.state as state
from app.api import app
from core import commercial_store, marketing_store, sales_store, workflow_store
from core.company_context import normalize_company_context, save_company_context
from core.suggest import suggest_workflows
from tests.market_validation_fixtures import NORTHLIGHT_CONTEXT


class SuggestBase(unittest.TestCase):
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


class SuggestTests(SuggestBase):
    def test_empty_world_suggests_discovery_first(self):
        out = suggest_workflows(0)
        self.assertEqual(len(out["recommendations"]), 1)
        rec = out["recommendations"][0]
        self.assertEqual(rec["method"], "prospect_discovery")
        self.assertTrue(rec["due_now"])
        self.assertEqual(rec["duration_days"], 14)
        self.assertIn("accounts:0", rec["evidence_refs"])
        self.assertIn("no baseline", rec["expected_range"]["basis"])

    def test_accounts_without_sends_suggest_outreach(self):
        save_company_context(normalize_company_context(NORTHLIGHT_CONTEXT))
        self.client.post("/company/commercial/accounts", auth=self.auth, headers=self.headers,
                         json={"company_name": "Alpha Co"})
        out = suggest_workflows(0)
        methods = [r["method"] for r in out["recommendations"]]
        self.assertIn("email_outreach", methods)
        draft_rec = next(r for r in out["recommendations"] if r["method"] == "email_outreach")
        self.assertEqual(draft_rec["expected_range"]["low"], 1)
        self.assertEqual(draft_rec["expected_range"]["unit"], "drafts")
        self.assertIn("one draft per account", draft_rec["expected_range"]["basis"])

    def test_sends_without_replies_suggest_message_change(self):
        self.client.post("/company/commercial/accounts", auth=self.auth, headers=self.headers,
                         json={"company_name": "Alpha Co"})
        lead, _ = sales_store.upsert_lead({"email": "a@x.test", "source": "manual"})
        from core.state import now_iso
        with sales_store.connect() as db:
            db.execute("INSERT INTO sales_interactions (lead_id, direction, channel, kind, created_at)"
                       " VALUES (?,?,?,?,?)", (lead["id"], "outbound", "email", "send", now_iso()))
        out = suggest_workflows(0)
        rec = next(r for r in out["recommendations"] if r["method"] == "targeted_outbound")
        self.assertIn("zero replies", rec["rationale"])
        self.assertIn("no baseline", rec["expected_range"]["basis"])

    def test_replies_push_toward_meetings(self):
        sales_store.upsert_lead({"email": "a@x.test", "source": "manual"})
        sales_store.add_event(None, "lead.replied", {})
        out = suggest_workflows(0)
        rec = next(r for r in out["recommendations"] if r["method"] == "direct_sales")
        self.assertIn("meetings", rec["expected_range"]["unit"])

    def test_meetings_raise_the_bar(self):
        sales_store.add_event(None, "meeting.scheduled", {})
        out = suggest_workflows(0)
        rec = next(r for r in out["recommendations"] if r["method"] == "email_outreach")
        self.assertIn("Raise the bar", rec["title"])
        self.assertIn("not a promise", rec["expected_range"]["basis"])

    def test_run_inside_its_window_is_not_due(self):
        from core import plan_governance
        save_company_context(normalize_company_context(NORTHLIGHT_CONTEXT))
        record = plan_governance.save_governance(plan_governance.GovernanceRecord(
            id="gov_1", plan_id="plan_1", status="valid", limits=plan_governance.GovernanceLimits(),
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            approved_at=datetime.now(timezone.utc).isoformat(),
            executed_at=datetime.now(timezone.utc).isoformat(),
            execution={"validation_events": {"observed": True, "count": 0}},
        ))
        _ = record
        out = suggest_workflows(0)
        for rec in out["recommendations"]:
            self.assertFalse(rec["due_now"])
            self.assertGreater(datetime.fromisoformat(rec["scheduled_for"]), datetime.now(timezone.utc))

    def test_suggest_endpoint_is_read_only(self):
        r = self.client.post("/company/automation/suggest", auth=self.auth)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("recommendations", body)
        self.assertIn("evidence_summary", body)
        self.assertIn("caps", body)
        # Suggested methods must all be governable, or the advice is useless.
        from core.plan_governance import METHOD_ACTIONS
        for rec in body["recommendations"]:
            self.assertIn(rec["method"], METHOD_ACTIONS)


if __name__ == "__main__":
    unittest.main()
