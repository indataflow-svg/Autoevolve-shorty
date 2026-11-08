"""Per-org quotas and the provider gate."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core import commercial_store, sales_store, state
from core.quotas import (
    QuotaExceeded,
    claim_provider,
    enforce_quota,
    org_plan,
    provider_limit,
    quota_snapshot,
    record_usage,
)


class QuotaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.old = (state.DB_PATH, commercial_store.DB_PATH, sales_store.DB_PATH)
        state.DB_PATH = commercial_store.DB_PATH = sales_store.DB_PATH = root / "company.db"
        state.init_db()
        sales_store.init_sales_db()
        commercial_store.init_commercial_db()

    def tearDown(self):
        state.DB_PATH, commercial_store.DB_PATH, sales_store.DB_PATH = self.old
        self.temp.cleanup()

    def test_free_plan_has_one_plan_run_publish_and_no_provider_calls(self):
        org = state.create_org("Free", "free-quota", plan="free")
        state.set_active_org(org["id"])
        self.assertEqual(org_plan(org["id"]), "free")
        enforce_quota(org["id"], "plans")
        record_usage(org["id"], "plans", "plan-1")
        with self.assertRaises(QuotaExceeded):
            enforce_quota(org["id"], "plans")
        self.assertEqual(provider_limit(org["id"], "prospeo"), 0)
        self.assertFalse(claim_provider(org["id"], "prospeo", "company_search"))

    def test_free_research_makes_no_provider_calls(self):
        from services.sales_service import research_market_leads

        org = state.create_org("Free Research", "free-research", plan="free")
        result = research_market_leads(industry="Logistics", org_id=org["id"])
        self.assertEqual(result["results"], [])
        self.assertTrue(any("quota" in warning or "free plan" in warning for warning in result["warnings"]))

    def test_paid_plan_allows_provider_requests_and_quota_snapshot(self):
        org = state.create_org("Paid", "paid-quota", plan="paid")
        state.set_active_org(org["id"])
        self.assertGreater(provider_limit(org["id"], "prospeo"), 0)
        self.assertTrue(claim_provider(org["id"], "prospeo", "company_search"))
        snapshot = quota_snapshot(org["id"], "plans")
        self.assertEqual(snapshot["plan"], "paid")
        self.assertEqual(snapshot["used"], 0)
        self.assertGreater(snapshot["limit"], 0)
        self.assertIn("reset_at", snapshot)

    def test_org_governance_limits_override_and_free_caps(self):
        from core.plan_governance import GovernanceLimits

        free = state.create_org("Free Limits", "free-limits", plan="free")
        state.set_org_limits(free["id"], {"max_spend_usd": 50, "max_outreach_contacts": 100, "max_duration_days": 30})
        limits = GovernanceLimits.load(free["id"])
        self.assertEqual(limits.max_spend_usd, 0)
        self.assertEqual(limits.max_outreach_contacts, 20)
        self.assertEqual(limits.max_duration_days, 14)
        paid = state.create_org("Paid Limits", "paid-limits", plan="paid")
        state.set_org_limits(paid["id"], {"max_spend_usd": 25, "max_outreach_contacts": 40, "max_duration_days": 10})
        paid_limits = GovernanceLimits.load(paid["id"])
        self.assertEqual(paid_limits.max_spend_usd, 25)
        self.assertEqual(paid_limits.max_outreach_contacts, 40)
        self.assertEqual(paid_limits.max_duration_days, 10)

    def test_usage_recording_is_idempotent(self):
        org = state.create_org("Paid2", "paid-quota-2", plan="paid")
        record_usage(org["id"], "plans", "same-plan")
        record_usage(org["id"], "plans", "same-plan")
        self.assertEqual(quota_snapshot(org["id"], "plans")["used"], 1)


if __name__ == "__main__":
    unittest.main()
