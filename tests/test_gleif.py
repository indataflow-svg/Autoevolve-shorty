"""Part A: free GLEIF entity resolution as step zero of the ladder.

Acceptance:
- parsing: a GLEIF payload yields LEI, legal name, jurisdiction, parent;
- miss/transport error returns None (never raises, never blocks the ladder);
- ladder: a GLEIF hit short-circuits before any paid client is constructed;
- explicit provider="gleif" with no record raises an honest ValueError.
"""
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import core.state as state
from core import sales_store

LEI_PAYLOAD = {
    "data": [{
        "id": "244800I5VYyg34KQT43",
        "type": "lei-records",
        "attributes": {
            "lei": "244800I5VYyg34KQT43",
            "entity": {
                "legalName": {"name": "Safaricom PLC"},
                "legalJurisdiction": "KE",
                "legalAddress": {"city": "Nairobi", "country": "KE"},
                "status": "ACTIVE",
            },
            "registration": {"status": "ISSUED", "managingLou": "BADFOLIO"},
        },
        "relationships": {
            "direct-parent": {"links": {"related": "https://api.gleif.org/api/v1/lei-records/PARENT/relationship"}},
        },
    }]
}
PARENT_PAYLOAD = {
    "data": {
        "id": "PARENTLEI000000000001",
        "type": "lei-records",
        "attributes": {
            "lei": "PARENTLEI000000000001",
            "entity": {"legalName": {"name": "Vodafone Group Plc"}},
        },
    }
}


def _urlopen_fake(url_or_request, *args, **kwargs):
    import urllib.request

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps(self._payload).encode("utf-8")

    url = url_or_request.full_url if isinstance(url_or_request, urllib.request.Request) else str(url_or_request)
    if "relationship" in url:
        return FakeResponse(PARENT_PAYLOAD)
    return FakeResponse(LEI_PAYLOAD)


class GleifParseTests(unittest.TestCase):
    def test_hit_extracts_identity_and_parent(self):
        from services import gleif

        with patch("services.gleif.urllib.request.urlopen", side_effect=_urlopen_fake):
            identity = gleif.resolve_identity("Safaricom")
        self.assertIsNotNone(identity)
        assert identity is not None
        self.assertEqual(identity["lei"], "244800I5VYyg34KQT43")
        self.assertEqual(identity["legal_name"], "Safaricom PLC")
        self.assertEqual(identity["jurisdiction"], "KE")
        self.assertEqual(identity["country"], "KE")
        self.assertEqual(identity["entity_status"], "ACTIVE")
        self.assertEqual(identity["identity_confidence"], "candidate-name-match")
        self.assertEqual(identity["direct_parent"], {
            "lei": "PARENTLEI000000000001", "legal_name": "Vodafone Group Plc"})

    def test_empty_name_never_calls_network(self):
        from services import gleif

        with patch("services.gleif.urllib.request.urlopen") as open_mock:
            self.assertIsNone(gleif.resolve_identity("  "))
            self.assertIsNone(gleif.resolve_identity(""))
            open_mock.assert_not_called()

    def test_miss_returns_none(self):
        from services import gleif

        with patch("services.gleif.urllib.request.urlopen") as open_mock:
            import urllib.request

            class Empty:
                def __enter__(self):
                    return self

                def __exit__(self, *exc):
                    return False

                def read(self):
                    return b'{"data": []}'

            open_mock.return_value = Empty()
            self.assertIsNone(gleif.resolve_identity("InDataFlow"))
            self.assertIsInstance(open_mock.call_args[0][0], urllib.request.Request)

    def test_transport_error_returns_none(self):
        import urllib.error

        from services import gleif

        with patch("services.gleif.urllib.request.urlopen",
                   side_effect=urllib.error.URLError("offline")):
            self.assertIsNone(gleif.resolve_identity("Safaricom"))


class GleifLadderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self._paths = (state.DB_PATH, sales_store.DB_PATH)
        state.DB_PATH = sales_store.DB_PATH = base / "company.db"
        state.init_db()
        sales_store.init_sales_db()
        self.env = patch.dict(os.environ, {"SALES_SEND_RECONCILE_ON_STARTUP": "false"}, clear=False)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        (state.DB_PATH, sales_store.DB_PATH) = self._paths
        self.temporary.cleanup()

    def test_hit_short_circuits_before_paid_clients(self):
        from core.sales_store import get_lead, upsert_lead
        from services.sales_service import resolve_company_profile

        lead, _ = upsert_lead({"company": "Safaricom PLC", "company_domain": "safaricom.co.ke", "source": "manual"})
        hit = {"lei": "244800I5VYyg34KQT43", "legal_name": "Safaricom PLC",
               "jurisdiction": "KE", "country": "KE", "city": "Nairobi",
               "entity_status": "ACTIVE", "registration_status": "ISSUED",
               "managing_lou": "BADFOLIO", "direct_parent": None,
               "identity_confidence": "candidate-name-match", "source": "gleif"}
        with patch("services.sales_service.gleif_service") as gleif_mock, \
             patch("services.sales_service.CompanyEnrichClient") as ce_mock, \
             patch("services.sales_service.PeopleDataLabsClient") as pdl_mock:
            gleif_mock.resolve_identity.return_value = hit
            result = resolve_company_profile(lead["id"], provider="auto", force=True)
            ce_mock.assert_not_called()
            pdl_mock.assert_not_called()
        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "gleif")
        self.assertTrue(result["free"])
        stored = get_lead(lead["id"])
        self.assertEqual(stored["company_profile"]["provider"], "gleif")
        self.assertEqual(stored["company_profile"]["summary"]["lei"], "244800I5VYyg34KQT43")
        # Lead already had a name: the candidate legal name must not overwrite it.
        self.assertEqual(stored["company"], "Safaricom PLC")

    def test_explicit_gleif_miss_raises(self):
        from core.sales_store import upsert_lead
        from services.sales_service import resolve_company_profile

        lead, _ = upsert_lead({"company": "No Such Company Ltd", "company_domain": "nosuch.test", "source": "manual"})
        with patch("services.sales_service.gleif_service") as gleif_mock:
            gleif_mock.resolve_identity.return_value = None
            with self.assertRaises(ValueError):
                resolve_company_profile(lead["id"], provider="gleif", force=True)

    def test_no_company_name_skips_gleif(self):
        from core.sales_store import upsert_lead
        from services.sales_service import resolve_company_profile

        lead, _ = upsert_lead({"email": "ops@example.com", "company_domain": "example.com", "source": "manual"})
        with patch("services.sales_service.gleif_service") as gleif_mock, \
             patch("services.sales_service.CompanyEnrichClient") as ce_mock:
            gleif_mock.resolve_identity.return_value = {"lei": "X"}
            ce_mock.return_value.enrich_company.return_value = {"company": {"name": "Example"}}
            ce_mock.return_value.extract_company_profile.return_value = {
                "name": "Example", "domain": "example.com", "location": {"country": None}}
            with patch.dict(os.environ, {"CE_API_KEY": "ce"}, clear=False):
                result = resolve_company_profile(lead["id"], provider="auto", force=True)
            gleif_mock.resolve_identity.assert_not_called()
        self.assertEqual(result["provider"], "companyenrich")


if __name__ == "__main__":
    unittest.main()
