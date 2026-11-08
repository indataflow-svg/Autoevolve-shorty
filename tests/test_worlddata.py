"""Part C: bulk world ingest -> local vintage-stamped store -> evidence.

Acceptance:
- pure parses for EDGAR tickers, CC captures, Companies House search;
- store upsert is idempotent and the summary answers coverage honestly;
- evidence union carries the world summary (absent -> not-present);
- Companies House without a key skips instead of failing.
"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import core.state as state
from core import worlddata_store

TICKERS = {
    "0": {"cik_str": "320193", "ticker": "AAPL", "title": "Apple Inc."},
    "1": {"cik_str": "0000789019", "ticker": "MSFT", "title": "MICROSOFT CORP"},
    "2": {"cik_str": "", "ticker": "XX", "title": ""},
}

CC_CAPTURES = [
    {"url": "indataflow.com/", "mime": "text/html", "timestamp": "20240101000000", "status": "200"},
    {"url": "indataflow.com/about", "mime": "text/html", "timestamp": "20250601000000", "status": "200"},
    {"url": "indataflow.com/logo.png", "mime": "image/png", "timestamp": "20250601000000", "status": "200"},
]

CH_SEARCH = {
    "items": [
        {"company_number": "12345678", "title": "IN DATA FLOW LTD",
         "company_status": "active", "company_type": "ltd",
         "date_of_creation": "2020-01-01",
         "address": {"locality": "Nairobi"}},
        {"company_number": "", "title": ""},
    ]
}


class ParseTests(unittest.TestCase):
    def test_edgar_tickers_parse(self):
        from services.worlddata import edgar

        records = edgar.parse_tickers(TICKERS)
        self.assertEqual(len(records), 2)
        apple = records[0]
        self.assertEqual((apple["ref"], apple["name"]), ("320193", "Apple Inc."))
        self.assertEqual(apple["data"]["ticker"], "AAPL")
        self.assertEqual(apple["source"], "edgar")
        limited = edgar.parse_tickers(TICKERS, limit=1)
        self.assertEqual(len(limited), 1)

    def test_commoncrawl_presence_fold(self):
        from services.worlddata import commoncrawl

        record = commoncrawl.parse_presence("InDataFlow.com", "CC-MAIN-2025-30", CC_CAPTURES)
        assert record is not None
        self.assertEqual(record["ref"], "indataflow.com")
        self.assertEqual(record["data"]["captures"], 3)
        self.assertEqual(record["data"]["first_seen"], "20240101000000")
        self.assertEqual(record["data"]["last_seen"], "20250601000000")
        self.assertEqual(record["vintage"], "CC-MAIN-2025-30")
        self.assertIsNone(commoncrawl.parse_presence("ghost.test", "CC-MAIN-2025-30", []))

    def test_companieshouse_parse(self):
        from services.worlddata import companieshouse

        records = companieshouse.parse_search(CH_SEARCH)
        self.assertEqual(len(records), 1)
        self.assertEqual((records[0]["ref"], records[0]["name"]), ("12345678", "IN DATA FLOW LTD"))
        self.assertEqual(records[0]["data"]["company_status"], "active")

    def test_companieshouse_unconfigured_skips(self):
        from services.worlddata import companieshouse

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("COMPANIES_HOUSE_API_KEY", None)
            with self.assertRaises(companieshouse.CompaniesHouseError):
                companieshouse.ingest(["test"])

    def test_edgar_fetch_uses_curl_and_parses(self):
        import json
        import subprocess

        from services.worlddata import edgar

        completed = subprocess.CompletedProcess(
            args=["curl"], returncode=0,
            stdout=json.dumps(TICKERS).encode(), stderr=b"")
        with patch("services.worlddata.edgar.shutil.which", return_value="/usr/bin/curl"), \
             patch("services.worlddata.edgar.subprocess.run", return_value=completed) as run_mock:
            payload = edgar.fetch_tickers()
            self.assertEqual(payload["0"]["ticker"], "AAPL")
            ua = run_mock.call_args[0][0]
            self.assertEqual(ua[0], "/usr/bin/curl")
            self.assertIn("-A", ua)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self._paths = (state.DB_PATH, worlddata_store.DB_PATH)
        state.DB_PATH = base / "company.db"
        worlddata_store.DB_PATH = base / "company.db"
        state.init_db()
        worlddata_store.init_worlddata_db()

    def tearDown(self):
        (state.DB_PATH, worlddata_store.DB_PATH) = self._paths
        self.temporary.cleanup()

    def test_upsert_idempotent_and_summary_honest(self):
        self.assertEqual(worlddata_store.sources_summary(),
                         {"present": False, "records": 0, "sources": []})
        worlddata_store.upsert_record("edgar", "listed_company", "320193",
                                      "Apple Inc.", {"ticker": "AAPL"}, "2026-01-01")
        worlddata_store.upsert_record("edgar", "listed_company", "320193",
                                      "Apple Inc.", {"ticker": "AAPL"}, "2026-01-01")
        self.assertEqual(worlddata_store.count_records(), 1)
        summary = worlddata_store.sources_summary()
        self.assertTrue(summary["present"])
        self.assertEqual(summary["records"], 1)
        self.assertEqual(summary["sources"][0]["source"], "edgar")
        self.assertEqual(summary["sources"][0]["min_vintage"], "2026-01-01")
        found = worlddata_store.find_records("edgar", "listed_company")
        self.assertEqual(found[0]["data"], {"ticker": "AAPL"})
        self.assertEqual(worlddata_store.clear_source("edgar"), 1)
        self.assertEqual(worlddata_store.count_records(), 0)

    def test_evidence_carries_world(self):
        from core.evidence import collect_evidence

        evidence = collect_evidence(0)
        self.assertIn("world", evidence)
        self.assertFalse(evidence["world"]["present"])
        worlddata_store.upsert_record("commoncrawl", "web_presence", "x.test",
                                      "x.test", {"captures": 2}, "CC-MAIN-2025-30")
        evidence = collect_evidence(0)
        self.assertTrue(evidence["world"]["present"])
        self.assertEqual(evidence["world"]["records"], 1)


class VerifyEndpointTests(unittest.TestCase):
    def setUp(self):
        import core.state as state
        from app.api import app
        from core import sales_store
        from fastapi.testclient import TestClient

        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self._paths = (state.DB_PATH, sales_store.DB_PATH, worlddata_store.DB_PATH)
        state.DB_PATH = sales_store.DB_PATH = base / "company.db"
        worlddata_store.DB_PATH = base / "company.db"
        state.init_db()
        sales_store.init_sales_db()
        worlddata_store.init_worlddata_db()
        self.env = patch.dict(os.environ, {
            "DASHBOARD_USER": "founder", "DASHBOARD_PASSWORD": "pw",
            "SALES_SEND_RECONCILE_ON_STARTUP": "false"}, clear=False)
        self.env.start()
        from app.api import app as application
        self.client = TestClient(application)
        self.auth = ("founder", "pw")

    def tearDown(self):
        import core.state as state
        from core import sales_store

        self.env.stop()
        (state.DB_PATH, sales_store.DB_PATH, worlddata_store.DB_PATH) = self._paths
        self.temporary.cleanup()

    def test_verify_reports_all_sources(self):
        worlddata_store.upsert_record(
            "commoncrawl", "web_presence", "safaricom.co.ke", "safaricom.co.ke",
            {"captures": 2, "first_seen": "20261015041948", "last_seen": "20261015041948"},
            "CC-MAIN-2026-43")
        hit = {"lei": "984500A80B648A7B9717", "legal_name": "Safaricom PLC",
               "country": "KE", "entity_status": "ACTIVE",
               "identity_confidence": "candidate-name-match"}
        with patch("app.companies_api.gleif_service") as gleif_mock:
            gleif_mock.resolve_identity.return_value = hit
            res = self.client.get(
                "/company/sales/companies/verify/lookup?domain=safaricom.co.ke&name=Safaricom PLC",
                auth=self.auth)
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertEqual(body["gleif"]["lei"], "984500A80B648A7B9717")
        self.assertEqual(body["gleif"]["country"], "KE")
        self.assertEqual(body["web_presence"]["vintage"], "CC-MAIN-2026-43")
        self.assertFalse(body["cached_profile"])

    def test_verify_empty_and_unauth(self):
        res = self.client.get("/company/sales/companies/verify/lookup", auth=self.auth)
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertIsNone(body["gleif"])
        self.assertIsNone(body["web_presence"])
        self.assertIsNone(body["domain"])
        self.assertEqual(
            self.client.get("/company/sales/companies/verify/lookup").status_code, 401)


if __name__ == "__main__":
    unittest.main()
