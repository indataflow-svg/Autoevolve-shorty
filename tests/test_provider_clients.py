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


class OpenCorporatesClientTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict("os.environ", {"OPENCORPORATES_API_KEY": "oc_test"}, clear=False)
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def _fake(self, payload=None, status=200):
        import urllib.error

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps(payload or {}).encode("utf-8")

        def fake_open(request, timeout=None):
            if status != 200:
                raise urllib.error.HTTPError(request.full_url, status, "error", hdrs=None, fp=io.BytesIO(b"{}"))
            fake_open.url = request.full_url
            return FakeResponse()

        return fake_open

    def test_search_builds_the_documented_query(self):
        from services.opencorporates import OpenCorporatesClient

        fake_open = self._fake({"results": {"companies": []}})
        with patch("urllib.request.urlopen", fake_open):
            self.assertEqual(OpenCorporatesClient().search_companies("Example", jurisdiction="ke"), [])
        self.assertIn("v0.4/companies/search", fake_open.url)
        self.assertIn("q=Example", fake_open.url)
        self.assertIn("jurisdiction_code=ke", fake_open.url)
        self.assertIn("api_token=oc_test", fake_open.url)

    def test_verify_accepts_only_an_exact_registry_match(self):
        from services.opencorporates import OpenCorporatesClient

        payload = {"results": {"companies": [
            {"company": {"name": "Example Logistics Limited", "company_number": "123", "jurisdiction_code": "ke"}},
            {"company": {"name": "Other Freight Ltd", "company_number": "999", "jurisdiction_code": "ke"}},
        ]}}
        with patch("urllib.request.urlopen", self._fake(payload)):
            hit = OpenCorporatesClient().verify_company("Example Logistics Limited", jurisdiction="ke")
            miss = OpenCorporatesClient().verify_company("Example Logistics", jurisdiction="ke")
        self.assertEqual(hit["company_number"], "123")
        self.assertIsNone(miss)

    def test_verify_rejects_a_wrong_jurisdiction_hit(self):
        from services.opencorporates import OpenCorporatesClient

        payload = {"results": {"companies": [
            {"company": {"name": "Example Logistics", "company_number": "1", "jurisdiction_code": "gb"}},
        ]}}
        with patch("urllib.request.urlopen", self._fake(payload)):
            self.assertIsNone(OpenCorporatesClient().verify_company("Example Logistics", jurisdiction="ke"))

    def test_missing_key_explains_where_to_get_one(self):
        from services.opencorporates import OpenCorporatesError, OpenCorporatesClient

        with patch.dict("os.environ", {"OPENCORPORATES_API_KEY": ""}, clear=False):
            with self.assertRaisesRegex(OpenCorporatesError, "free"):
                OpenCorporatesClient()

    def test_quota_and_auth_errors_are_distinct(self):
        from services.opencorporates import OpenCorporatesClient, OpenCorporatesError

        with patch("urllib.request.urlopen", self._fake(status=403)):
            with self.assertRaisesRegex(OpenCorporatesError, "quota"):
                OpenCorporatesClient().search_companies("Example")
        with patch("urllib.request.urlopen", self._fake(status=401)):
            with self.assertRaises(OpenCorporatesError):
                OpenCorporatesClient().search_companies("Example")


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
