"""Evidence union and account suggestions: every source counts, unknowns stay unknown."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import core.state as state
from app.api import app
from core import commercial_store, sales_store
from core.company_context import normalize_company_context, save_company_context
from core.evidence import collect_evidence, suggest_accounts


class EvidenceBase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self._paths = (state.DB_PATH, commercial_store.DB_PATH, sales_store.DB_PATH)
        state.DB_PATH = commercial_store.DB_PATH = sales_store.DB_PATH = base / "company.db"
        state.init_db()
        sales_store.init_sales_db()
        commercial_store.init_commercial_db()
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
        state.DB_PATH, commercial_store.DB_PATH, sales_store.DB_PATH = self._paths
        self.temporary.cleanup()


class EvidenceTests(EvidenceBase):
    def test_empty_world_is_unknown_not_zero_claims(self):
        ev = collect_evidence(0)
        self.assertFalse(ev["context"]["present"])
        self.assertEqual(ev["accounts"]["total"], 0)
        self.assertEqual(ev["leads"]["total"], 0)
        self.assertEqual(ev["engagement"]["channels"], {})
        self.assertEqual(ev["history"], [])

    def test_every_source_appears_with_counts(self):
        from tests.market_validation_fixtures import NORTHLIGHT_CONTEXT
        save_company_context(normalize_company_context(NORTHLIGHT_CONTEXT))
        self.client.post("/company/commercial/accounts", auth=self.auth, headers=self.headers,
                         json={"company_name": "Claimed", "domain": "claimed.test"})
        sales_store.upsert_lead({"email": "a@claimed.test", "company_domain": "claimed.test",
                                 "source": "website"})
        sales_store.upsert_lead({"email": "b@wild.test", "company": "Wild Co",
                                 "company_domain": "wild.test", "source": "hunter"})
        sales_store.upsert_lead({"email": "c@wild.test", "company_domain": "wild.test",
                                 "source": "hunter",
                                 "metadata": {"company_candidate": True}})
        sales_store.add_event(None, "lead.replied", {})
        ev = collect_evidence(0)
        self.assertTrue(ev["context"]["present"])
        self.assertEqual(ev["accounts"]["total"], 1)
        self.assertEqual(ev["leads"]["total"], 3)
        self.assertEqual(ev["leads"]["candidates"], 1)
        # Claimed domains are not proposed again; wild ones are, with reasons.
        self.assertEqual([u["domain"] for u in ev["leads"]["unlinked_domains"]], ["wild.test"])
        wild = ev["leads"]["unlinked_domains"][0]
        self.assertEqual(wild["lead_count"], 2)
        self.assertTrue(wild["has_candidate"])
        self.assertEqual(ev["engagement"]["replies"], 1)

    def test_channel_rates_unknown_without_sends(self):
        sales_store.upsert_lead({"email": "a@x.test", "source": "manual"})
        ev = collect_evidence(0)
        self.assertEqual(ev["engagement"]["channels"], {})

    def test_evidence_endpoint_is_read_only(self):
        r = self.client.get("/company/automation/evidence", auth=self.auth)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        for key in ("context", "offers", "icps", "accounts", "leads", "imports",
                    "engagement", "history", "channels"):
            self.assertIn(key, body)
        # No founder token needed: nothing can be written through it.
        self.assertNotIn("X-Founder-Action-Token", str(r.headers))


class SuggestTests(EvidenceBase):
    def test_suggestions_come_with_reasons_and_create_cleanly(self):
        from tests.market_validation_fixtures import NORTHLIGHT_CONTEXT
        save_company_context(normalize_company_context(NORTHLIGHT_CONTEXT))
        sales_store.upsert_lead({"email": "a@wild.test", "company": "Wild Co",
                                 "company_domain": "wild.test", "source": "hunter"})
        out = suggest_accounts(0)
        self.assertEqual(out["total"], 1)
        sug = out["suggestions"][0]
        self.assertEqual(sug["domain"], "wild.test")
        self.assertIn("hunter", sug["reason"])
        self.assertIn("no account yet", sug["reason"])
        # Confirming passes the same validation and dedupe as manual entry.
        created = self.client.post("/company/commercial/accounts", auth=self.auth,
                                   headers=self.headers,
                                   json={"company_name": sug["company_name"],
                                         "domain": sug["domain"]}).json()
        self.assertEqual(created["domain"], "wild.test")
        self.assertEqual(suggest_accounts(0)["total"], 0)

    def test_similar_names_without_shared_domain_stay_separate(self):
        sales_store.upsert_lead({"email": "a@acme.test", "company": "Acme",
                                 "company_domain": "acme.test", "source": "manual"})
        sales_store.upsert_lead({"email": "b@other.test", "company": "Acme Similar",
                                 "source": "manual"})
        out = suggest_accounts(0)
        self.assertEqual([s["domain"] for s in out["suggestions"]], ["acme.test"])

    def test_suggest_endpoint_needs_no_token(self):
        r = self.client.post("/company/commercial/accounts/suggest", auth=self.auth)
        self.assertEqual(r.status_code, 200)
        self.assertIn("suggestions", r.json())


if __name__ == "__main__":
    unittest.main()
