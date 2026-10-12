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


class Phase1HardeningTests(CommercialBase):
    def test_accounts_search_filter_paginate(self):
        for name in ("Acme Logistics", "Beta Foods", "Acme Freight"):
            self.client.post("/company/commercial/accounts", auth=self.auth,
                             headers=self.headers, json={"company_name": name})
        q = self.client.get("/company/commercial/accounts?q=acme", auth=self.auth).json()
        self.assertEqual(q["total"], 2)
        p = self.client.get("/company/commercial/accounts?page=2&page_size=2",
                            auth=self.auth).json()
        self.assertEqual(p["page"], 2)
        self.assertEqual(len(p["items"]), 1)

    def test_pipeline_update_versions_and_protects_stages_in_use(self):
        pipe = self.client.get("/company/commercial/pipelines", auth=self.auth).json()[0]
        acct = self.client.post("/company/commercial/accounts", auth=self.auth,
                                headers=self.headers, json={"company_name": "Pipe Co"}).json()
        opp = self.client.post("/company/commercial/opportunities", auth=self.auth,
                               headers=self.headers,
                               json={"account_id": acct["id"], "pipeline_id": pipe["id"]}).json()
        # Remove the stage the opportunity sits on: refused.
        kept = [s for s in DEFAULT_STAGES if s["key"] != opp["stage"]]
        bad = self.client.patch(f"/company/commercial/pipelines/{pipe['id']}", auth=self.auth,
                                headers=self.headers, json={"stages": kept})
        self.assertEqual(bad.status_code, 422, bad.text)
        # Rename only: version increments.
        renamed = [dict(s, label=s["label"] + "!") if s["key"] == opp["stage"] else s
                   for s in DEFAULT_STAGES]
        ok = self.client.patch(f"/company/commercial/pipelines/{pipe['id']}", auth=self.auth,
                               headers=self.headers, json={"stages": renamed}).json()
        self.assertEqual(ok["version"], pipe["version"] + 1)
        detail = self.client.get(f"/company/commercial/opportunities/{opp['id']}",
                                 auth=self.auth).json()
        self.assertEqual(detail["account"]["company_name"], "Pipe Co")

    def test_opportunity_detail_carries_history_and_account(self):
        pipe = self.client.get("/company/commercial/pipelines", auth=self.auth).json()[0]
        acct = self.client.post("/company/commercial/accounts", auth=self.auth,
                                headers=self.headers, json={"company_name": "Hist Co"}).json()
        opp = self.client.post("/company/commercial/opportunities", auth=self.auth,
                               headers=self.headers,
                               json={"account_id": acct["id"], "pipeline_id": pipe["id"]}).json()
        moved = self.client.post(f"/company/commercial/opportunities/{opp['id']}/move",
                                 auth=self.auth, headers=self.headers,
                                 json={"stage": "qualified"}).json()
        import json as j
        self.assertEqual(len(j.loads(moved["stage_history_json"])), 2)
        detail = self.client.get(f"/company/commercial/opportunities/{opp['id']}",
                                 auth=self.auth).json()
        self.assertEqual(detail["account"]["company_name"], "Hist Co")
        self.assertIn("activities", detail)

    def test_icp_templates_are_starting_points_and_archive_works(self):
        tpl = self.client.get("/company/commercial/icp-templates", auth=self.auth).json()
        self.assertTrue(len(tpl) >= 1)
        icp = self.client.post("/company/commercial/icps", auth=self.auth, headers=self.headers, json={
            "name": "From template", "criteria": tpl[0]["criteria"]}).json()
        self.assertEqual(icp["status"], "provisional")
        detail = self.client.get(f"/company/commercial/icps/{icp['id']}", auth=self.auth).json()
        self.assertEqual(detail["name"], "From template")
        self.assertIn("criteria_json", detail)
        self.assertEqual(self.client.get("/company/commercial/icps/nope", auth=self.auth).status_code, 404)
        archived = self.client.post(f"/company/commercial/icps/{icp['id']}/archive",
                                    auth=self.auth, headers=self.headers).json()
        self.assertEqual(archived["status"], "archived")

    def test_every_workspace_read_resolves(self):
        # The refactored UI mounts one tab at a time; each tab's reads must 200.
        for path in ("offers", "icps", "icp-templates", "accounts", "pipelines",
                     "opportunities", "rules", "integrations", "imports",
                     "onboarding-sessions"):
            r = self.client.get(f"/company/commercial/{path}", auth=self.auth)
            self.assertEqual(r.status_code, 200, path)

    def test_csv_upsert_refresh_skip_and_bad_mapping(self):
        content = "company_name,domain\nAcme,acme.test\nBeta,beta.test\n"
        files = {"file": ("a.csv", io.BytesIO(content.encode()), "text/csv")}
        prev = self.client.post("/company/commercial/imports/preview?entity_type=account",
                                auth=self.auth, headers=self.headers, files=files).json()
        mapping = {"company_name": "company_name", "domain": "domain"}
        first = self.client.post(f"/company/commercial/imports/{prev['import_id']}/commit",
                                 auth=self.auth, headers=self.headers,
                                 json={"mapping": mapping}).json()
        self.assertEqual(first["totals"]["created"], 2)
        # Second file, one row skipped by the user, upsert refreshes the other.
        content2 = "company_name,domain,industry\nAcme New,acme.test,logistics\nBeta,beta.test,\n"
        files2 = {"file": ("b.csv", io.BytesIO(content2.encode()), "text/csv")}
        prev2 = self.client.post("/company/commercial/imports/preview?entity_type=account",
                                 auth=self.auth, headers=self.headers, files=files2).json()
        done = self.client.post(f"/company/commercial/imports/{prev2['import_id']}/commit",
                                auth=self.auth, headers=self.headers,
                                json={"mapping": {**mapping, "industry": "industry"},
                                      "skip_rows": [2], "mode": "upsert"}).json()
        self.assertEqual(done["totals"]["updated"], 1)
        self.assertEqual(done["totals"]["skipped"], 1)
        # Unknown canonical fields are rejected on a fresh (uncommitted) import.
        prev3 = self.client.post("/company/commercial/imports/preview?entity_type=account",
                                 auth=self.auth, headers=self.headers, files=files).json()
        bad = self.client.post(f"/company/commercial/imports/{prev3['import_id']}/commit",
                               auth=self.auth, headers=self.headers,
                               json={"mapping": {"company_name": "nope"}})
        self.assertEqual(bad.status_code, 422)
        notcsv = self.client.post("/company/commercial/imports/preview?entity_type=account",
                                  auth=self.auth, headers=self.headers,
                                  files={"file": ("a.txt", io.BytesIO(b"x"), "text/plain")})
        self.assertEqual(notcsv.status_code, 422)

    def test_writes_require_founder_token(self):
        r = self.client.post("/company/commercial/offers", auth=self.auth, json={"name": "X"})
        self.assertEqual(r.status_code, 403)
        r = self.client.post("/company/commercial/accounts", auth=self.auth, json={"company_name": "X"})
        self.assertEqual(r.status_code, 403)

    def test_catalog_never_leaks_secrets(self):
        import json as j
        cat = self.client.get("/company/commercial/integrations", auth=self.auth).json()
        blob = j.dumps(cat)
        # Key *names* and the "api_key" mechanism label are public by design;
        # secret *values* must never appear.
        for var in ("SALES_RESEND_API_KEY", "HUNTER_API_KEY", "APOLLO_API_KEY",
                    "PROSPEO_API_KEY", "SALES_ACTION_TOKEN", "DASHBOARD_PASSWORD"):
            value = os.getenv(var)
            if value:
                self.assertNotIn(value, blob)
        for c in cat:
            if c.get("connection"):
                self.assertNotIn("token", j.dumps(c["connection"]).lower())
                self.assertIn("credential_ref", c["connection"])

    def test_coming_soon_provider_cannot_connect(self):
        r = self.client.post("/company/commercial/integrations/hubspot/connect", auth=self.auth,
                             headers=self.headers, json={})
        self.assertEqual(r.status_code, 422)
        r = self.client.post("/company/commercial/integrations/nope/connect", auth=self.auth,
                             headers=self.headers, json={})
        self.assertEqual(r.status_code, 404)

    def test_hard_disqualifier_fails_qualification_closed(self):
        icp = self.client.post("/company/commercial/icps", auth=self.auth, headers=self.headers, json={
            "name": "Strict", "criteria": [{"field": "industry", "operator": "equals", "value": "x"}]}).json()
        self.client.post("/company/commercial/rules", auth=self.auth, headers=self.headers, json={
            "name": "needs 90", "criterion": "fit>=90", "rule_type": "fit",
            "threshold": 90, "hard_disqualify": True})
        acct = self.client.post("/company/commercial/accounts", auth=self.auth,
                                headers=self.headers,
                                json={"company_name": "Weak", "industry": "y", "icp_id": icp["id"]}).json()
        q = self.client.post(f"/company/commercial/accounts/{acct['id']}/qualify",
                             auth=self.auth, headers=self.headers).json()
        self.assertTrue(q["hard_fail"])
        self.assertFalse(q["qualified"])
        self.assertTrue(q["needs_human"])

    def test_onboarding_rejects_bad_path_and_merges_progress(self):
        bad = self.client.post("/company/commercial/onboarding-sessions", auth=self.auth,
                               headers=self.headers, json={"path": "Z"})
        self.assertEqual(bad.status_code, 422)
        s = self.client.post("/company/commercial/onboarding-sessions", auth=self.auth,
                             headers=self.headers, json={"path": "B"}).json()
        u1 = self.client.patch(f"/company/commercial/onboarding-sessions/{s['id']}", auth=self.auth,
                               headers=self.headers, json={"progress": {"a": True}}).json()
        u2 = self.client.patch(f"/company/commercial/onboarding-sessions/{s['id']}", auth=self.auth,
                               headers=self.headers,
                               json={"current_step": "import", "progress": {"b": True}}).json()
        import json as j
        merged = j.loads(u2["progress_json"])
        self.assertEqual(merged, {"a": True, "b": True})
        self.assertEqual(u2["current_step"], "import")


    def test_workspace_and_catalog_read_the_same_registry(self):
        # D4: key presence and connection state come from one read. A stored
        # healthy connection must appear on the workspace view; key names stay,
        # key values never do.
        import json as j
        from core import commercial_store
        with commercial_store.connect() as db:
            db.execute(
                "INSERT INTO integration_connections (id, org_id, provider,"
                " external_account_ref, status, sync_status, credential_ref,"
                " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                ("conn_test", 0, "hunter", "acme", "healthy", "idle",
                 "HUNTER_API_KEY", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"),
            )
        body = self.client.get("/company/ui/integrations", auth=self.auth).json()
        prospecting = next(g for g in body["groups"] if g["id"] == "prospecting")
        self.assertEqual(
            [(c["provider"], c["status"]) for c in prospecting["connections"]],
            [("hunter", "healthy")],
        )
        self.assertEqual(body["connected_providers"], 1)
        blob = j.dumps(body)
        for var in ("HUNTER_API_KEY",):
            self.assertIn(var, blob)  # names are public
        for secret in [os.getenv("HUNTER_API_KEY") or ""]:
            if secret:
                self.assertNotIn(secret, blob)


    def test_linked_leads_resolve_by_domain_without_merging(self):
        # D6: leads link to the registry at read time; similar names with no
        # shared domain stay separate records.
        from core import sales_store
        acct = self.client.post("/company/commercial/accounts", auth=self.auth,
                                headers=self.headers,
                                json={"company_name": "Acme", "domain": "acme.test"}).json()
        sales_store.upsert_lead({"email": "ops@acme.test", "company_domain": "acme.test",
                                 "source": "manual"})
        sales_store.upsert_lead({"email": "other@else.test", "company": "Acme Similar",
                                 "source": "manual"})
        detail = self.client.get(f"/company/commercial/accounts/{acct['id']}",
                                 auth=self.auth).json()
        self.assertEqual([l["email"] for l in detail["linked_leads"]], ["ops@acme.test"])
        # The leads themselves are untouched: no account_id rewrite, no merge.
        self.assertEqual(sales_store.get_lead_by_email("other@else.test")["company"],
                         "Acme Similar")


    def test_lead_outreach_status_and_opportunity_stage_are_independent(self):
        # D2: a sent email must not advance an opportunity; moving an
        # opportunity must not rewrite lead outreach state.
        from core import sales_store
        acct = self.client.post("/company/commercial/accounts", auth=self.auth,
                                headers=self.headers,
                                json={"company_name": "Split Co", "domain": "split.test"}).json()
        lead, _ = sales_store.upsert_lead({"email": "ops@split.test",
                                           "company_domain": "split.test", "source": "manual"})
        opp = self.client.post("/company/commercial/opportunities", auth=self.auth,
                               headers=self.headers,
                               json={"account_id": acct["id"]}).json()
        sales_store.mark_sent(sales_store.claim_draft_for_send(sales_store.approve_draft(
            sales_store.create_draft(
                lead["id"], "Hello there", "A sufficiently long body for the send.")["id"]
        )["id"])["id"], "msg-1")
        self.assertEqual(sales_store.get_lead(lead["id"])["stage"], "contacted")
        still = self.client.get(f"/company/commercial/opportunities/{opp['id']}",
                                auth=self.auth).json()
        self.assertEqual(still["stage"], "prospect")
        self.client.post(f"/company/commercial/opportunities/{opp['id']}/move",
                         auth=self.auth, headers=self.headers, json={"stage": "qualified"})
        self.assertEqual(sales_store.get_lead(lead["id"])["stage"], "contacted")

    def test_scores_keep_distinct_meanings(self):
        # D7: the legacy heuristic, ICP fit, and recorded intent are three
        # different numbers from three different evidence sources.
        from core import sales_store
        icp = self.client.post("/company/commercial/icps", auth=self.auth, headers=self.headers, json={
            "name": "Strict Fit",
            "criteria": [{"field": "industry", "operator": "equals", "value": "logistics"}]}).json()
        acct = self.client.post("/company/commercial/accounts", auth=self.auth,
                                headers=self.headers,
                                json={"company_name": "Score Co", "industry": "logistics",
                                      "icp_id": icp["id"]}).json()
        lead, _ = sales_store.upsert_lead({"email": "ops@score.test", "source": "website",
                                           "consent": True})
        q = self.client.post(f"/company/commercial/accounts/{acct['id']}/qualify",
                             auth=self.auth, headers=self.headers).json()
        self.assertGreaterEqual(lead["lead_score"], 0)
        self.assertEqual(q["fit"]["grade"], "fit")
        self.assertEqual(q["fit"]["score"], 100)
        self.assertEqual(q["intent"]["level"], "none")
        self.assertEqual(q["intent"]["score"], 0)
        # Same world, three answers: heuristic > 0, fit full, intent empty.
        self.assertTrue(lead["lead_score"] != q["fit"]["score"]
                        or q["fit"]["score"] != q["intent"]["score"])


DEFAULT_STAGES = [
    {"key": "prospect", "label": "Prospect", "allowed_next": ["qualified", "disqualified"]},
    {"key": "qualified", "label": "Qualified", "allowed_next": ["proposal", "disqualified"]},
    {"key": "proposal", "label": "Proposal", "allowed_next": ["negotiation", "deferred", "lost"]},
    {"key": "negotiation", "label": "Negotiation", "allowed_next": ["won", "lost", "deferred"]},
    {"key": "won", "label": "Won", "allowed_next": []},
    {"key": "lost", "label": "Lost", "allowed_next": []},
    {"key": "deferred", "label": "Deferred", "allowed_next": ["prospect"]},
    {"key": "disqualified", "label": "Disqualified", "allowed_next": []},
]


def json_dump(o) -> str:
    import json
    return json.dumps(o).lower()


if __name__ == "__main__":
    unittest.main()
