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
    clear_company_context,
    context_from_onboarding,
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

    def test_onboarding_projection_uses_confirmed_answers_only(self):
        context = context_from_onboarding(
            start={"name": "Example Studio", "objective": "Get first customers", "market": "United States"},
            confirm={
                "name": "Example Studio", "website": "https://studio.test",
                "description": "Builds operations tools.", "industry": "Software",
                "positioning": "Operations teams get clear records.",
                "offer_summary": "A guided operations workflow.",
                "ideal_customer": "Midmarket operations teams",
                "product_name": "Ops Audit",
                "problem": "Handoffs are manual",
                "pricing": "$2k per month",
                "marketing_stage": "starting_from_zero",
            },
        )
        self.assertEqual(context.market.market, "United States")
        self.assertEqual(context.objective.primary_goal, "Get first customers")
        self.assertEqual(context.product.value_proposition, "Operations teams get clear records.")
        self.assertEqual(context.offer.description, "A guided operations workflow.")
        self.assertEqual(context.offer.pricing, "$2k per month")
        self.assertEqual(context.customer.industry, "Software")
        self.assertEqual(context.status, "context_complete")
        self.assertEqual(context.evidence.traction, [])  # never answered, never filled
        self.assertIsNone(context.resources.budget)


class CompanyContextApiTests(unittest.TestCase):
    """Onboarding writes the canonical context; the API reads and replaces it."""

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

    def post(self, suffix: str, payload: dict):
        return self.client.post(
            f"/company/setup/onboarding/{suffix}", auth=self.auth,
            headers=self.headers, json=payload,
        )

    def start_company(self):
        response = self.post("company", {
            "name": "Example Studio", "website": "https://studio.test",
            "objective": "Get first customers", "market": "United States",
        })
        self.assertEqual(response.status_code, 200, response.text)

    def confirm(self, **extra):
        payload = {
            "name": "Example Studio", "website": "https://studio.test",
            "description": "Example Studio builds operations tools.",
            "industry": "Software", "positioning": "Operations teams get clear records.",
            "offer_summary": "A guided operations workflow.",
        } | extra
        response = self.post("company/confirm", payload)
        self.assertEqual(response.status_code, 200, response.text)

    def context(self, *, anonymous: bool = False):
        auth = None if anonymous else self.auth
        return self.client.get("/company/context", auth=auth)

    def stored_context(self, **kwargs) -> dict:
        """The canonical sections as the founder confirmed them."""
        body = self.context(**kwargs).json()
        return body["context"]

    def test_onboarding_stores_the_canonical_context(self):
        self.assertEqual(self.context(anonymous=True).status_code, 401)
        self.assertEqual(self.context().json()["status"], "context_incomplete")
        self.start_company()
        self.confirm(
            product_name="Ops Audit", ideal_customer="Midmarket operations teams",
            problem="Handoffs are manual", existing_customers="Acme Systems",
            testimonials="Operations Director, Acme Systems",
            marketing_stage="starting_from_zero",
        )
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

        # The stored record survives reload and a fresh API process state.
        self.assertEqual(get_company_context().product.name, "Ops Audit")

    def test_minimal_onboarding_marks_the_context_incomplete(self):
        self.start_company()
        self.confirm()
        stored = self.stored_context()
        self.assertEqual(stored["status"], "context_incomplete")
        self.assertEqual(stored["missing"], ["product", "customer", "problem"])
        self.assertIsNone(stored["product"]["name"])
        self.assertEqual(stored["state"]["marketing_stage"], "starting_from_zero")
        self.assertEqual(stored["company"]["description"], "Example Studio builds operations tools.")

    def test_unknown_values_are_never_filled_in(self):
        self.start_company()
        self.confirm(product_name="   ", problem="", testimonials=[" ", ""])
        stored = self.stored_context()
        self.assertIsNone(stored["product"]["name"])
        self.assertIsNone(stored["market"]["problem"])
        self.assertEqual(stored["evidence"]["testimonials"], [])
        self.assertIn("product", stored["missing"])

    def test_existing_confirmed_program_is_projected_into_the_context(self):
        self.start_company()
        self.confirm(product_name="Ops Audit", problem="Handoffs are manual")
        # Simulate a program confirmed before the canonical context existed:
        # the record is gone, the founder's confirmed answers are not.
        clear_company_context()
        self.assertIsNone(get_company_context())
        projected = self.stored_context()
        self.assertEqual(projected["company"]["name"], "Example Studio")
        self.assertEqual(projected["objective"]["primary_goal"], "Get first customers")
        self.assertEqual(projected["company"]["description"], "Example Studio builds operations tools.")
        self.assertEqual(projected["product"]["name"], "Ops Audit")
        self.assertIsNotNone(get_company_context().updated_at)  # projected once, then stored

    def test_api_update_replaces_the_stored_context(self):
        self.start_company()
        self.confirm(product_name="Ops Audit", problem="Handoffs are manual")
        updated = self.client.put("/company/context", auth=self.auth, headers=self.headers, json={
            "company": {"name": "Example Studio Renamed", "website": "https://studio.test/"},
            "state": {"marketing_stage": "Starting from zero"},
        })
        self.assertEqual(updated.status_code, 200, updated.text)
        body = updated.json()["context"]
        self.assertEqual(body["company"]["name"], "Example Studio Renamed")
        self.assertIsNone(body["product"]["name"])  # replaced, not merged
        self.assertEqual(body["state"]["marketing_stage"], "starting_from_zero")
        self.assertEqual(self.stored_context()["company"]["name"], "Example Studio Renamed")

    def test_an_existing_company_can_correct_its_confirmed_answers(self):
        self.start_company()
        self.confirm(product_name="Ops Audit", ideal_customer="Midmarket ops teams", pricing="$2,000 per month")
        self.confirm(
            product_name="Ops Audit Plus", ideal_customer="Midmarket ops teams",
            problem="Handoffs are manual", pricing="$3,000 per month",
        )
        stored = self.stored_context()
        self.assertEqual(stored["product"]["name"], "Ops Audit Plus")
        self.assertEqual(stored["offer"]["pricing"], "$3,000 per month")
        self.assertEqual(stored["status"], "context_complete")
        self.assertEqual(get_company_context().product.name, "Ops Audit Plus")

    def test_api_validation_errors_and_authorization(self):
        denied = self.client.put("/company/context", auth=self.auth, json={
            "company": {"name": "Example Studio"},
        })
        self.assertEqual(denied.status_code, 403)
        empty = self.client.put("/company/context", auth=self.auth, headers=self.headers, json={})
        self.assertEqual(empty.status_code, 422)
        self.assertIn("at least one company context fact", empty.json()["detail"])
        bad_stage = self.client.put("/company/context", auth=self.auth, headers=self.headers, json={
            "company": {"name": "Example Studio"}, "state": {"marketing_stage": "already running ads"},
        })
        self.assertEqual(bad_stage.status_code, 422)
        self.assertIn("marketing stage", str(bad_stage.json()["detail"]).lower())
        bad_site = self.client.put("/company/context", auth=self.auth, headers=self.headers, json={
            "company": {"website": "https://user:secret@studio.test"},
        })
        self.assertEqual(bad_site.status_code, 422)
        self.assertIsNone(get_company_context())

    def test_api_never_returns_credentials_from_stored_urls(self):
        self.start_company()
        self.confirm()
        response = self.client.put("/company/context", auth=self.auth, headers=self.headers, json={
            "company": {"name": "Example Studio", "website": "https://studio.test/?access_token=secret"},
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["context"]["company"]["website"], "https://studio.test")
        self.assertNotIn("secret", response.text)


if __name__ == "__main__":
    unittest.main()