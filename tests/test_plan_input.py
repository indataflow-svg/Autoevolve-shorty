"""PlanInput contract: org-scoped, deterministic, and evidence-backed."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core import commercial_store, sales_store, state
from core.company_context import clear_company_context, normalize_company_context, save_company_context
from core.plan_input import PlanInputError, build_plan_input, get_plan_input, save_plan_input
from tests.market_validation_fixtures import NORTHLIGHT_CONTEXT


class PlanInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.old = (state.DB_PATH, sales_store.DB_PATH, commercial_store.DB_PATH)
        state.DB_PATH = sales_store.DB_PATH = commercial_store.DB_PATH = self.root / "company.db"
        state.init_db()
        sales_store.init_sales_db()
        commercial_store.init_commercial_db()
        self.org = state.create_org("Plan Input", "plan-input")
        state.set_active_org(self.org["id"])

    def tearDown(self):
        state.DB_PATH, sales_store.DB_PATH, commercial_store.DB_PATH = self.old
        self.temp.cleanup()

    def test_requires_context(self):
        with self.assertRaises(PlanInputError):
            build_plan_input(self.org["id"])

    def test_context_is_org_scoped(self):
        save_company_context(normalize_company_context(NORTHLIGHT_CONTEXT), self.org["id"])
        other = state.create_org("Other", "plan-input-other")
        with self.assertRaises(PlanInputError):
            build_plan_input(other["id"])
        clear_company_context(self.org["id"])

    def test_hash_is_stable_and_input_contains_digest_and_constraints(self):
        save_company_context(normalize_company_context(NORTHLIGHT_CONTEXT), self.org["id"])
        first = build_plan_input(self.org["id"])
        second = build_plan_input(self.org["id"])
        self.assertEqual(first["input_hash"], second["input_hash"])
        self.assertEqual(first["schema"], "company-core.plan-input.v1")
        self.assertEqual(first["org_id"], self.org["id"])
        self.assertIn("context", first)
        self.assertIn("evidence", first)
        self.assertIn("last_run", first)
        self.assertIn("constraints", first)
        self.assertEqual(first["evidence"]["leads"]["total"], 0)
        self.assertEqual(first["last_run"]["observed"], False)
        self.assertIsNone(first["last_run"]["cost_usd"])
        self.assertIn("allowed_methods", first["constraints"])

    def test_input_is_persisted_by_hash(self):
        save_company_context(normalize_company_context(NORTHLIGHT_CONTEXT), self.org["id"])
        payload = build_plan_input(self.org["id"])
        save_plan_input(payload)
        restored = get_plan_input(self.org["id"], payload["input_hash"])
        self.assertIsNotNone(restored)
        self.assertEqual(restored["context"]["company"]["name"], "Northlight Ops")


if __name__ == "__main__":
    unittest.main()
