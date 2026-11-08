"""Canonical company context: normalization, completeness, storage, and API."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import core.state as state
from app.api import app
from core.company_context import (
    get_company_context,
    normalize_company_context,
    save_company_context,
)


class CompanyContextCoreTests(unittest.TestCase):
    """Normalization and validation without the HTTP layer."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.old_state = state.DB_PATH
        state.DB_PATH = Path(self.temporary.name) / "company.db"
        state.init_db()

    def tearDown(self):
        state.DB_PATH = self.old_state
        self.temporary.cleanup()

    def test_raw_answers_become_a_canonical_context_without_being_reworded(self):
        context = normalize_company_context({
            "company": {
                "name": "  Example   Studio \n",
                "website": "Studio.test/About?token=secret",
                "description": "Builds  operations\ntools",
            },
            "product": {"name": "Ops Audit", "value_proposition": "  Clear records  "},
            "customer": {"ideal_customer": "Midmarket ops teams", "buyer_roles": "Ops Director\nOps Director\nVP Ops"},
            "market": {"problem": "Handoffs are manual"},
            "objective": {"primary_goal": "Get first customers"},
            "state": {"marketing_stage": "Starting from zero"},
        })
        self.assertEqual(context.company.name, "Example Studio")
        self.assertEqual(context.company.description, "Builds operations tools")
        self.assertEqual(context.product.value_proposition, "Clear records")
        self.assertEqual(context.customer.buyer_roles, ["Ops Director", "VP Ops"])
        self.assertEqual(context.state.marketing_stage, "starting_from_zero")
        self.assertEqual(context.status, "context_complete")
        self.assertEqual(context.missing, [])

        # Unanswered fields stay unknown, and a public website keeps no token.
        self.assertIsNone(context.company.geography)
        self.assertIsNone(context.customer.industry)
        self.assertEqual(context.evidence.testimonials, [])
        self.assertEqual(context.constraints.operational, [])
        self.assertEqual(context.company.website, "https://studio.test/About")

    def test_partial_input_is_kept_and_reported_incomplete(self):
        context = normalize_company_context({"company": {"name": "Example Studio"}})
        self.assertEqual(context.status, "context_incomplete")
        self.assertEqual(
            context.missing, ["product", "customer", "problem", "objective", "marketing_stage"]
        )
        self.assertIsNone(context.product.name)
        self.assertIsNone(context.state.marketing_stage)
        self.assertEqual(context.completeness_percent, 17)
        self.assertFalse(context.workflow_ready)

    def test_company_name_is_optional_and_identity_counts_without_it(self):
        # A description or website alone counts the company group: the name
        # stays optional and never blocks workflow preparation by itself.
        for identity in (
            {"description": "Ops tools for midmarket teams"},
            {"website": "https://studio.test"},
        ):
            context = normalize_company_context({"company": identity})
            self.assertIsNone(context.company.name)
            self.assertNotIn("company", context.missing)

    def test_completeness_reaches_workflow_ready_at_80_percent(self):
        context = normalize_company_context({
            "company": {"description": "Ops tools"},
            "product": {"name": "Ops Audit"},
            "customer": {"ideal_customer": "Midmarket ops teams"},
            "market": {"problem": "Handoffs are manual"},
            "objective": {"primary_goal": "Get first customers"},
        })
        self.assertEqual(context.missing, ["marketing_stage"])
        self.assertEqual(context.completeness_percent, 83)
        self.assertTrue(context.workflow_ready)
        self.assertEqual(context.status, "context_incomplete")

    def test_blank_and_null_answers_are_unknown_rather_than_invented(self):
        context = normalize_company_context({
            "company": {"name": "Example Studio", "website": "   "},
            "product": {"description": None, "category": ""},
            "evidence": {"testimonials": "Acme\n\n  acme  \nBeta"},
        })
        self.assertIsNone(context.company.website)
        self.assertIsNone(context.product.description)
        self.assertIsNone(context.product.category)
        self.assertEqual(context.evidence.testimonials, ["Acme", "Beta"])

    def test_known_marketing_stage_wording_maps_and_unknown_stages_are_rejected(self):
        for wording in ("starting_from_zero", "Starting from zero", "start from scratch"):
            self.assertEqual(
                normalize_company_context({"state": {"marketing_stage": wording}}).state.marketing_stage,
                "starting_from_zero",
            )
        with self.assertRaises(ValueError):
            normalize_company_context({"state": {"marketing_stage": "in a good place already"}})
        with self.assertRaises(ValueError):
            normalize_company_context({"company": {"website": "not a website at all?"}})

    def test_context_survives_a_fresh_read_and_an_update_replaces_it(self):
        save_company_context(normalize_company_context({
            "company": {"name": "Example Studio"},
            "state": {"marketing_stage": "starting_from_zero"},
        }))
        stored = get_company_context()
        self.assertEqual(stored.company.name, "Example Studio")
        self.assertIsNotNone(stored.updated_at)

        save_company_context(normalize_company_context({"product": {"name": "Ops Audit"}}))
        replaced = get_company_context()
        self.assertEqual(replaced.product.name, "Ops Audit")
        self.assertIsNone(replaced.company.name)  # a replacement never keeps stale claims
        self.assertIn("company", replaced.missing)



class CompanyContextApiTests(unittest.TestCase):
    """The canonical context API stores, reads, and replaces founder answers."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.old_state = state.DB_PATH
        state.DB_PATH = Path(self.temporary.name) / "company.db"
        state.init_db()
        self.env = patch.dict(os.environ, {
            "DASHBOARD_USER": "founder", "DASHBOARD_PASSWORD": "dashboard-secret",
            "SALES_ACTION_TOKEN": "action-secret", "SALES_SEND_RECONCILE_ON_STARTUP": "false",
        }, clear=False)
        self.env.start()
        self.client = TestClient(app)
        self.auth = ("founder", "dashboard-secret")
        self.headers = {"X-Founder-Action-Token": "action-secret"}

    def tearDown(self):
        self.env.stop()
        state.DB_PATH = self.old_state
        self.temporary.cleanup()

    def put(self, payload: dict):
        return self.client.put("/company/context", auth=self.auth, headers=self.headers, json=payload)

    def context(self, *, anonymous: bool = False):
        return self.client.get("/company/context", auth=None if anonymous else self.auth)

    def stored_context(self, **kwargs) -> dict:
        return self.context(**kwargs).json()["context"]

    def full_payload(self) -> dict:
        return {
            "company": {
                "name": "Example Studio", "website": "https://studio.test",
                "description": "Example Studio builds operations tools.",
            },
            "product": {"name": "Ops Audit", "description": "A guided operations workflow."},
            "customer": {"ideal_customer": "Midmarket operations teams"},
            "market": {"problem": "Handoffs are manual", "market": "United States"},
            "objective": {"primary_goal": "Get first customers"},
            "state": {"marketing_stage": "starting_from_zero"},
            "evidence": {"existing_customers": ["Acme Systems"]},
        }

    def test_context_api_stores_the_canonical_context(self):
        self.assertEqual(self.context(anonymous=True).status_code, 401)
        self.assertEqual(self.context().json()["status"], "context_incomplete")
        response = self.put(self.full_payload())
        self.assertEqual(response.status_code, 200, response.text)
        stored = self.stored_context()
        self.assertEqual(stored["status"], "context_complete")
        self.assertEqual(stored["missing"], [])
        self.assertEqual(stored["company"]["name"], "Example Studio")
        self.assertEqual(stored["company"]["website"], "https://studio.test")
        self.assertEqual(stored["product"]["name"], "Ops Audit")
        self.assertEqual(stored["customer"]["ideal_customer"], "Midmarket operations teams")
        self.assertEqual(stored["market"]["problem"], "Handoffs are manual")
        self.assertEqual(stored["market"]["market"], "United States")
        self.assertEqual(stored["evidence"]["existing_customers"], ["Acme Systems"])
        self.assertEqual(stored["objective"]["primary_goal"], "Get first customers")
        self.assertEqual(stored["state"]["marketing_stage"], "starting_from_zero")
        self.assertEqual(stored["schema_version"], 1)
        self.assertIsNotNone(stored["updated_at"])
        self.assertEqual(get_company_context().product.name, "Ops Audit")

    def test_partial_context_marks_the_context_incomplete(self):
        response = self.put({"company": {"name": "Example Studio"}})
        self.assertEqual(response.status_code, 200, response.text)
        stored = self.stored_context()
        self.assertEqual(stored["status"], "context_incomplete")
        self.assertEqual(
            stored["missing"], ["product", "customer", "problem", "objective", "marketing_stage"]
        )
        self.assertIsNone(stored["product"]["name"])

    def test_unknown_values_are_never_filled_in(self):
        response = self.put({
            "company": {"name": "Example Studio"},
            "product": {"name": "   "},
            "market": {"problem": ""},
            "evidence": {"testimonials": [" ", ""]},
        })
        self.assertEqual(response.status_code, 200, response.text)
        stored = self.stored_context()
        self.assertIsNone(stored["product"]["name"])
        self.assertIsNone(stored["market"]["problem"])
        self.assertEqual(stored["evidence"]["testimonials"], [])
        self.assertIn("product", stored["missing"])

    def test_api_update_replaces_the_stored_context(self):
        self.assertEqual(self.put(self.full_payload()).status_code, 200)
        updated = self.put({
            "company": {"name": "Example Studio Renamed", "website": "https://studio.test/"},
            "state": {"marketing_stage": "Starting from zero"},
        })
        self.assertEqual(updated.status_code, 200, updated.text)
        body = updated.json()["context"]
        self.assertEqual(body["company"]["name"], "Example Studio Renamed")
        self.assertIsNone(body["product"]["name"])  # replaced, not merged
        self.assertEqual(body["state"]["marketing_stage"], "starting_from_zero")
        self.assertEqual(self.stored_context()["company"]["name"], "Example Studio Renamed")

    def test_api_can_correct_existing_answers(self):
        self.assertEqual(self.put(self.full_payload()).status_code, 200)
        payload = self.full_payload()
        payload["product"]["name"] = "Ops Audit Plus"
        payload["offer"] = {"pricing": "$3,000 per month"}
        self.assertEqual(self.put(payload).status_code, 200)
        stored = self.stored_context()
        self.assertEqual(stored["product"]["name"], "Ops Audit Plus")
        self.assertEqual(stored["offer"]["pricing"], "$3,000 per month")
        self.assertEqual(stored["status"], "context_complete")

    def test_api_validation_errors_and_authorization(self):
        denied = self.client.put("/company/context", auth=self.auth, json={"company": {"name": "Example Studio"}})
        self.assertEqual(denied.status_code, 403)
        empty = self.client.put("/company/context", auth=self.auth, headers=self.headers, json={})
        self.assertEqual(empty.status_code, 422)
        self.assertIn("at least one company context fact", empty.json()["detail"])
        bad_stage = self.put({
            "company": {"name": "Example Studio"},
            "state": {"marketing_stage": "already running ads"},
        })
        self.assertEqual(bad_stage.status_code, 422)
        self.assertIn("marketing stage", str(bad_stage.json()["detail"]).lower())
        bad_site = self.put({"company": {"website": "https://user:secret@studio.test"}})
        self.assertEqual(bad_site.status_code, 422)
        self.assertIsNone(get_company_context())

    def test_api_never_returns_credentials_from_stored_urls(self):
        response = self.put({
            "company": {"name": "Example Studio", "website": "https://studio.test/?access_token=secret"},
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["context"]["company"]["website"], "https://studio.test")
        self.assertNotIn("secret", response.text)
