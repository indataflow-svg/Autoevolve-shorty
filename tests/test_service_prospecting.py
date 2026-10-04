"""Bounded contact previews use multiple providers without automatic reveal calls."""

import io
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

import core.sales_store as sales_store
import core.state as state
from services.service_prospecting import search_service_contacts
from services.prospeo import ProspeoClient, ProspeoError


class ServiceProspectingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.old_state = state.DB_PATH
        self.old_sales = sales_store.DB_PATH
        db = Path(self.temporary.name) / "company.db"
        state.DB_PATH = sales_store.DB_PATH = db
        state.init_db()
        sales_store.init_sales_db()
        self.env = patch.dict(os.environ, {
            "APOLLO_API_KEY": "fixture", "PROSPEO_API_KEY": "fixture", "LUSHA_API_KEY": "fixture",
            "SERVICE_APOLLO_PREVIEW_CAP_24H": "5", "SERVICE_PROSPEO_PREVIEW_CAP_24H": "1",
            "SERVICE_LUSHA_PREVIEW_CAP_24H": "0",
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()
        state.DB_PATH = self.old_state
        sales_store.DB_PATH = self.old_sales
        self.temporary.cleanup()

    def test_falls_through_to_one_prospeo_page_and_respects_local_cap(self):
        apollo = [{
            "id": "apollo-1", "first_name": "Alex", "last_name": "Lee", "title": "Practice Manager",
            "organization": {"name": "Bright Dental", "primary_domain": "bright.test"},
        }]
        prospeo = {"results": [
            {"person": {"person_id": "prospeo-1", "full_name": "Alex Lee", "current_job_title": "Practice Manager"},
             "company": {"name": "Bright Dental", "website": "bright.test"}},
            {"person": {"person_id": "prospeo-2", "full_name": "Sam Rivera", "current_job_title": "Owner"},
             "company": {"name": "Clear Dental", "website": "clear.test"}},
        ]}
        with patch("services.service_prospecting.ApolloClient") as apollo_client, \
             patch("services.service_prospecting.ProspeoClient") as prospeo_client, \
             patch("services.service_prospecting.LushaClient") as lusha_client:
            apollo_client.return_value.people_service_search.return_value = apollo
            prospeo_client.return_value.search_person.return_value = prospeo
            first = search_service_contacts(
                keywords=["Dental clinics", "appointment scheduling"], buyer_titles=["Practice Manager"],
                market=None, desired_contacts=2,
            )
            self.assertEqual(len(first["results"]), 2)
            self.assertEqual([lead["full_name"] for lead in first["results"]], ["Alex Lee", "Sam Rivera"])
            self.assertEqual(first["providers"], {"apollo": 1, "prospeo": 2})
            self.assertTrue(all(not lead.get("email") for lead in first["results"]))
            apollo_client.return_value.people_service_search.assert_called_once()
            prospeo_client.return_value.search_person.assert_called_once()
            lusha_client.assert_not_called()
            second = search_service_contacts(
                keywords=["Dental clinics"], buyer_titles=["Practice Manager"],
                market=None, desired_contacts=2,
            )
            self.assertEqual(len(second["results"]), 1)
            self.assertIn("prospeo local 24-hour search cap reached", second["warnings"])
            prospeo_client.return_value.search_person.assert_called_once()

    def test_apollo_fulfills_small_request_without_spending_prospeo_request(self):
        with patch("services.service_prospecting.ApolloClient") as apollo_client, \
             patch("services.service_prospecting.ProspeoClient") as prospeo_client:
            apollo_client.return_value.people_service_search.return_value = [{
                "id": "apollo-1", "name": "Alex Lee", "title": "Practice Manager",
                "organization": {"name": "Bright Dental", "primary_domain": "bright.test"},
            }]
            result = search_service_contacts(
                keywords=["Dental clinics"], buyer_titles=["Practice Manager"],
                market="United States", desired_contacts=1,
            )
            self.assertEqual(len(result["results"]), 1)
            prospeo_client.assert_not_called()

    def test_suppressed_contact_is_excluded_and_falls_through(self):
        blocked, _ = sales_store.upsert_lead({
            "full_name": "Alex Lee", "company": "Bright Dental", "company_domain": "bright.test",
            "source": "manual",
        })
        sales_store.suppress_lead(blocked["id"], "do not contact")
        with patch("services.service_prospecting.ApolloClient") as apollo_client, \
             patch("services.service_prospecting.ProspeoClient") as prospeo_client:
            apollo_client.return_value.people_service_search.return_value = [{
                "id": "apollo-1", "name": "Alex Lee", "organization": {"name": "Bright Dental", "primary_domain": "bright.test"},
            }]
            prospeo_client.return_value.search_person.return_value = {"results": [{
                "person": {"person_id": "prospeo-2", "full_name": "Sam Rivera"},
                "company": {"name": "Clear Dental", "website": "clear.test"},
            }]}
            result = search_service_contacts(
                keywords=["Dental clinics"], buyer_titles=["Practice Manager"],
                market=None, desired_contacts=1,
            )
        self.assertEqual([lead["full_name"] for lead in result["results"]], ["Sam Rivera"])

    def test_prospeo_no_results_with_broad_market_is_a_completed_empty_search(self):
        with patch.dict(os.environ, {"APOLLO_API_KEY": "", "LUSHA_API_KEY": ""}), \
             patch("services.service_prospecting.ProspeoClient") as prospeo_client:
            prospeo_client.return_value.search_suggestions.return_value = {"location_suggestions": []}
            prospeo_client.return_value.search_person.side_effect = ProspeoError(
                "NO_RESULTS", 400, "NO_RESULTS",
            )
            result = search_service_contacts(
                keywords=["AI training data", "machine learning datasets"],
                buyer_titles=["Head of AI", "Director of Machine Learning"],
                market="Africa", desired_contacts=5,
            )
            filters = prospeo_client.return_value.search_person.call_args.args[0]
            self.assertEqual(filters["company_keywords"]["include"], ["AI training data", "machine learning datasets"])
            self.assertNotIn("company_location_search", filters)
            self.assertEqual(result["completed_providers"], ["prospeo"])
            self.assertEqual(result["providers"], {"prospeo": 0})
            self.assertEqual(result["results"], [])
            self.assertTrue(any("no contacts" in warning for warning in result["warnings"]))
            self.assertTrue(any("Africa" in warning for warning in result["warnings"]))
            self.assertFalse(any("unavailable" in warning for warning in result["warnings"]))

    def test_prospeo_uses_exact_location_from_free_suggestions(self):
        with patch.dict(os.environ, {"APOLLO_API_KEY": "", "LUSHA_API_KEY": ""}), \
             patch("services.service_prospecting.ProspeoClient") as prospeo_client:
            prospeo_client.return_value.search_suggestions.return_value = {
                "location_suggestions": [{"name": "United States", "type": "COUNTRY"}],
            }
            prospeo_client.return_value.search_person.return_value = {"results": []}
            result = search_service_contacts(
                keywords=["dental practice"], buyer_titles=["Practice Manager"],
                market="united states", desired_contacts=2,
            )
            filters = prospeo_client.return_value.search_person.call_args.args[0]
            self.assertEqual(filters["company_location_search"], {"include": ["United States"]})
            self.assertEqual(result["warnings"], [])

    def test_prospeo_client_preserves_no_results_error_code(self):
        response = urllib.error.HTTPError(
            "https://api.prospeo.io/search-person", 400, "Bad Request", {},
            io.BytesIO(b'{"error":true,"error_code":"NO_RESULTS"}'),
        )
        with patch("urllib.request.urlopen", side_effect=response):
            with self.assertRaises(ProspeoError) as caught:
                ProspeoClient("fixture").search_person({"person_job_title": {"include": ["Practice Manager"]}})
        self.assertEqual(caught.exception.status, 400)
        self.assertEqual(caught.exception.error_code, "NO_RESULTS")
