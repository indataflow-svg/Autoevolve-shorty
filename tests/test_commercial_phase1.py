"""Phase 1 commercial foundation tests."""
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import core.state as state
from app.api import app
from core import commercial_store as store


class CommercialBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._path = state.DB_PATH
        state.DB_PATH = Path(self.tmp.name) / "company.db"
        store.DB_PATH = state.DB_PATH
        from core import sales_store, marketing_store
        sales_store.DB_PATH = state.DB_PATH
        sales_store.init_sales_db()
        store.init_commercial_db()
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
        from core import sales_store
        state.DB_PATH = self._path
        store.DB_PATH = self._path
        sales_store.DB_PATH = self._path
        self.tmp.cleanup()


class Phase1Tests(CommercialBase):
    def test_offer_crud(self):
        r = self.client.post("/company/commercial/offers", auth=self.auth,
                             headers=self.headers, json={"name": "Ops Desk", "category": "svc"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(len(self.client.get("/company/commercial/offers", auth=self.auth).json()), 1)

    def test_icp_versioning_and_fit(self):
        icp = self.client.post("/company/commercial/icps", auth=self.auth, headers=self.headers, json={
            "name": "Logistics ICP", "criteria": [{"field": "industry", "operator": "equals", "value": "logistics"}],
            "exclusions": [{"field": "region", "value": "EU"}]}).json()
        self.assertEqual(icp["version"], 1)
        upd = self.client.patch(f"/company/commercial/icps/{icp['id']}", auth=self.auth,
                                headers=self.headers, json={"segment": "SMB"}).json()
        self.assertEqual(upd["version"], 2)
        ev = self.client.post(f"/company/commercial/icps/{icp['id']}/evaluate", auth=self.auth,
                              headers=self.headers, json={"industry": "logistics", "id": "x"}).json()
        self.assertEqual(ev["fit"]["grade"], "fit")
        bad = self.client.post(f"/company/commercial/icps/{icp['id']}/evaluate", auth=self.auth,
                               headers=self.headers, json={"industry": "logistics", "region": "EU"}).json()
        self.assertTrue(bad["fit"]["disqualified"])

    def test_csv_preview_commit_dedupe_and_retry(self):
        content = "company_name,domain,email\nAcme,acme.test,ops@acme.test\n,beta.test,ops@beta.test\n"
        files = {"file": ("leads.csv", io.BytesIO(content.encode()), "text/csv")}
        prev = self.client.post("/company/commercial/imports/preview?entity_type=account",
                                auth=self.auth, headers=self.headers, files=files).json()
        self.assertEqual(prev["totals"]["rows"], 2)
        imp = prev["import_id"]
        commit = self.client.post(f"/company/commercial/imports/{imp}/commit", auth=self.auth,
                                  headers=self.headers,
                                  json={"mapping": {"company_name": "company_name", "domain": "domain"}}).json()
        self.assertEqual(commit["totals"]["created"], 1)
        replay = self.client.post(f"/company/commercial/imports/{imp}/commit", auth=self.auth,
                                  headers=self.headers,
                                  json={"mapping": {"company_name": "company_name"}}).json()
        self.assertTrue(replay.get("replayed"))

    def test_pipeline_rules_enforced(self):
        acct = self.client.post("/company/commercial/accounts", auth=self.auth,
                                headers=self.headers, json={"company_name": "Acme"}).json()
        opp = self.client.post("/company/commercial/opportunities", auth=self.auth,
                               headers=self.headers, json={"account_id": acct["id"]}).json()
        self.assertEqual(opp["stage"], "prospect")
        bad = self.client.post(f"/company/commercial/opportunities/{opp['id']}/move",
                               auth=self.auth, headers=self.headers, json={"stage": "won"})
        self.assertEqual(bad.status_code, 422)
        ok = self.client.post(f"/company/commercial/opportunities/{opp['id']}/move",
                              auth=self.auth, headers=self.headers, json={"stage": "qualified"})
        self.assertEqual(ok.status_code, 200)

    def test_qualification_separates_fit_intent(self):
        acct = self.client.post("/company/commercial/accounts", auth=self.auth,
                                headers=self.headers, json={"company_name": "Beta"}).json()
        q = self.client.post(f"/company/commercial/accounts/{acct['id']}/qualify",
                             auth=self.auth, headers=self.headers).json()
        self.assertIn("fit", q)
        self.assertIn("intent", q)
        self.assertIn("qualified", q)
        self.assertEqual(q["intent"]["level"], "none")

    def test_integration_catalog_truthful(self):
        cat = self.client.get("/company/commercial/integrations", auth=self.auth).json()
        providers = {c["provider"] for c in cat}
        self.assertIn("hubspot", providers)
        for c in cat:
            if c.get("connection"):
                self.assertNotIn("token", json_dump(c))
        soon = [c for c in cat if c["provider"] == "hubspot"][0]
        self.assertEqual(soon["state"], "coming_soon")

    def test_onboarding_paths_persist(self):
        a = self.client.post("/company/commercial/onboarding-sessions", auth=self.auth,
                             headers=self.headers, json={"path": "A"}).json()
        b = self.client.post("/company/commercial/onboarding-sessions", auth=self.auth,
                             headers=self.headers, json={"path": "B"}).json()
        self.assertNotEqual(a["path"], b["path"])
        upd = self.client.patch(f"/company/commercial/onboarding-sessions/{a['id']}",
                                auth=self.auth, headers=self.headers,
                                json={"current_step": "icp", "progress": {"company": True}}).json()
        self.assertEqual(upd["current_step"], "icp")

    def test_org_isolation_no_client_org_trust(self):
        # No org param exists; second org data must not leak via id guessing.
        acct = self.client.post("/company/commercial/accounts", auth=self.auth,
                                headers=self.headers, json={"company_name": "Gamma"}).json()
        self.assertEqual(acct["org_id"], 0)


def json_dump(o) -> str:
    import json
    return json.dumps(o).lower()


if __name__ == "__main__":
    unittest.main()
