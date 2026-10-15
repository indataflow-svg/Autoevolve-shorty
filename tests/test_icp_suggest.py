"""ICP criterion suggestions mined from the founder's own records.

Every proposal carries its support count, every field its fill rate, and thin
evidence warns instead of pretending. Nothing here invents a buyer.
"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import core.state as state
from app.api import app
from core import commercial_store


class SuggestBase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self._paths = (state.DB_PATH, commercial_store.DB_PATH)
        state.DB_PATH = commercial_store.DB_PATH = base / "company.db"
        state.init_db()
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
        state.DB_PATH, commercial_store.DB_PATH = self._paths
        self.temporary.cleanup()

    def add_account(self, **fields):
        payload = {"company_name": "Anon Co"}
        payload.update(fields)
        response = self.client.post("/company/commercial/accounts", auth=self.auth,
                                   headers=self.headers, json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def suggest(self):
        response = self.client.get("/company/commercial/icps/suggest-criteria", auth=self.auth)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()


class SuggestTests(SuggestBase):
    def test_empty_world_says_so(self):
        out = self.suggest()
        self.assertEqual(out["basis"], {"set": "none", "count": 0})
        self.assertEqual(out["suggestions"], [])
        self.assertEqual(len(out["warnings"]), 1)

    def test_customers_outrank_everything(self):
        for _ in range(3):
            self.add_account(industry="logistics", lifecycle_status="customer")
        self.add_account(industry="retail", lifecycle_status="engaged")
        self.add_account(industry="retail", lifecycle_status="target")
        out = self.suggest()
        self.assertEqual(out["basis"], {"set": "customers", "count": 3})
        industry = next(s for s in out["suggestions"] if s["field"] == "industry")
        self.assertEqual(industry["value"], "logistics")
        self.assertEqual((industry["support"], industry["total"]), (3, 3))
        self.assertEqual(industry["source"], "evidence")

    def test_falls_back_to_engaged_then_all(self):
        self.add_account(industry="retail", lifecycle_status="engaged")
        out = self.suggest()
        self.assertEqual(out["basis"], {"set": "engaged", "count": 1})
        self.add_account(industry="retail", lifecycle_status="target")
        self.add_account(industry="retail", lifecycle_status="target")
        out = self.suggest()
        # Engaged still wins while any exist.
        self.assertEqual(out["basis"]["set"], "engaged")

    def test_fill_rates_expose_unfillable_fields(self):
        self.add_account(industry="logistics", lifecycle_status="customer")
        out = self.suggest()
        rates = {r["field"]: (r["known"], r["total"]) for r in out["fill_rates"]}
        self.assertEqual(rates["industry"], (1, 1))
        self.assertEqual(rates["region"], (0, 1))
        self.assertIn("thin evidence", " ".join(out["warnings"]))

    def test_no_thin_warning_with_enough_evidence(self):
        for i in range(3):
            self.add_account(company_name=f"Customer {i}", industry="logistics",
                             lifecycle_status="customer")
        out = self.suggest()
        self.assertEqual(out["warnings"], [])

    def test_literal_route_beats_the_id_route(self):
        # Would 404 as "icp not found" if /icps/{rid} swallowed this path.
        self.add_account(industry="logistics", lifecycle_status="customer")
        out = self.suggest()
        self.assertIn("suggestions", out)


if __name__ == "__main__":
    unittest.main()
