"""Provider client contract tests: Lusha V3 shapes and CompanyEnrich extraction.

These pin the wire format against the vendors' published OpenAPI specs, so a
drift in our favour (wrong keys that the provider ignores or rejects) fails
here instead of silently degrading research quality in production.
"""

import io
import json
import unittest
import urllib.error
from unittest.mock import patch


def _response(payload: dict) -> object:
    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(payload).encode("utf-8")

    return _FakeResponse()


def _http_error(url: str, status: int, payload: dict) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url, status, "error", {}, io.BytesIO(json.dumps(payload).encode("utf-8"))
    )


class LushaClientTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict("os.environ", {"LUSHA_API_KEY": "test-key"}, clear=False)
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def _capture_body(self, payload):
        bodies = []

        def fake_open(request, timeout=None):
            bodies.append(json.loads(request.data.decode("utf-8")) if request.data else None)
            return _response(payload)

        return fake_open, bodies

    def test_prospect_sends_documented_filters(self):
        from services.lusha import LushaClient

        fake_open, bodies = self._capture_body({"requestId": "r1", "results": []})
        with patch("urllib.request.urlopen", fake_open):
            LushaClient().prospect_contacts(
                job_title="Operations Manager",
                service_keywords=["logistics"],
                location="Kenya",
                company_size="11-50",
                limit=3,
            )
        body = bodies[0]
        self.assertEqual(body["pagination"], {"page": 0, "size": 10})
        self.assertEqual(body["filters"]["contacts"]["include"]["jobTitles"], ["Operations Manager"])
        self.assertEqual(body["filters"]["contacts"]["include"]["locations"], [{"country": "Kenya"}])
        self.assertEqual(body["filters"]["companies"]["include"]["keywords"], ["logistics"])
        self.assertEqual(body["filters"]["companies"]["include"]["sizes"], [{"min": 11, "max": 50}])
        self.assertEqual(body["options"], {"maxContactsPerCompany": 1})

    def test_prospect_omits_unparseable_size_instead_of_sending_garbage(self):
        from services.lusha import LushaClient

        fake_open, bodies = self._capture_body({"requestId": "r1", "results": []})
        with patch("urllib.request.urlopen", fake_open):
            LushaClient().prospect_contacts(service_keywords=["freight"], company_size="huge", limit=5)
        self.assertNotIn("sizes", bodies[0]["filters"]["companies"]["include"])
        self.assertEqual(bodies[0]["filters"]["companies"]["include"]["keywords"], ["freight"])

    def test_enrich_sends_ids_and_reveal(self):
        from services.lusha import LushaClient

        fake_open, bodies = self._capture_body({"results": []})
        with patch("urllib.request.urlopen", fake_open):
            LushaClient().enrich_contacts(["c1", "c2"])
        self.assertEqual(bodies[0], {"ids": ["c1", "c2"], "reveal": ["emails", "phones"]})

    def test_enrich_rejects_empty_contact_list(self):
        from services.lusha import LushaClient

        with self.assertRaises(ValueError):
            LushaClient().enrich_contacts([])

    def test_payment_and_permission_failures_are_not_retried(self):
        from services.lusha import LushaClient

        calls = []

        def fake_open(request, timeout=None):
            calls.append(request.full_url)
            raise _http_error(request.full_url, 402, {"statusCode": 402, "message": "Insufficient credits"})

        with patch("urllib.request.urlopen", fake_open):
            with self.assertRaisesRegex(Exception, "Insufficient credits"):
                LushaClient().enrich_contacts(["c1"])
        self.assertEqual(len(calls), 1)

    def test_error_detail_includes_validation_errors(self):
        from services.lusha import LushaClient, LushaError

        def fake_open(request, timeout=None):
            raise _http_error(request.full_url, 400, {
                "statusCode": 400, "message": "Invalid request parameters",
                "errors": ["size must be between 10 and 100"],
            })

        with patch("urllib.request.urlopen", fake_open):
            with self.assertRaises(LushaError) as ctx:
                LushaClient().prospect_contacts(service_keywords=["x"], limit=5)
        self.assertIn("size must be between 10 and 100", str(ctx.exception))


class CompanyEnrichExtractTests(unittest.TestCase):
    def test_extract_reads_nested_location_and_socials(self):
        from services.company_enrich import CompanyEnrichClient

        client = CompanyEnrichClient.__new__(CompanyEnrichClient)
        profile = client.extract_company_profile({
            "id": "123e4567-e89b-12d3-a456-426614174000",
            "name": "Example Logistics",
            "domain": "example.com",
            "website": "https://example.com",
            "industry": "Logistics",
            "industries": ["Logistics"],
            "employees": "51-200",
            "revenue": "10m-50m",
            "location": {
                "country": {"code": "KE", "name": "Kenya"},
                "state": {"name": "Nairobi County"},
                "city": {"name": "Nairobi"},
            },
            "socials": {"linkedin_url": "https://www.linkedin.com/company/example-logistics"},
            "keywords": ["freight", "customs"],
            "technologies": ["SAP"],
        })
        self.assertEqual(profile["location"], {"city": "Nairobi", "state": "Nairobi County", "country": "Kenya"})
        self.assertEqual(profile["linkedin_url"], "https://www.linkedin.com/company/example-logistics")
        self.assertEqual(profile["employee_range"], "51-200")
        self.assertEqual(profile["revenue_range"], "10m-50m")
        self.assertEqual(profile["industry"], "Logistics")
        # CompanyInfo has no specialities/target-market fields: nothing may be
        # invented from unrelated keys.
        self.assertEqual(profile["specialties"], [])
        self.assertEqual(profile["target_markets"], [])

    def test_extract_tolerates_plain_string_location(self):
        from services.company_enrich import CompanyEnrichClient

        client = CompanyEnrichClient.__new__(CompanyEnrichClient)
        profile = client.extract_company_profile({
            "name": "Plain Co", "location": {"city": "Kigali", "country": "Rwanda"},
        })
        self.assertEqual(profile["location"], {"city": "Kigali", "state": None, "country": "Rwanda"})


if __name__ == "__main__":
    unittest.main()
