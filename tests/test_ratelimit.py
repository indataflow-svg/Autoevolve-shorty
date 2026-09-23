import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import ratelimit
from app.api import app
import core.sales_store as sales_store
import core.state as state


class RateLimitTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        database = Path(self.temporary.name) / "company.db"
        self.original = (state.DB_PATH, sales_store.DB_PATH)
        state.DB_PATH = database
        sales_store.DB_PATH = database
        state.init_db()
        sales_store.init_sales_db()
        ratelimit.reset()
        self.client = TestClient(app)

    def tearDown(self):
        ratelimit.reset()
        state.DB_PATH, sales_store.DB_PATH = self.original
        self.temporary.cleanup()

    def test_intake_burst_over_the_limit_returns_429_and_creates_no_lead(self):
        with patch.dict(os.environ, {
            "RATE_LIMIT_ENABLED": "true",
            "RATE_LIMIT_INTAKE_PER_MINUTE": "2",
            "SALES_INTAKE_SECRET": "intake-secret",
        }, clear=False):
            responses = [self.client.post("/integrations/leads/website", json={}) for _ in range(3)]
        statuses = [r.status_code for r in responses]
        self.assertNotIn(429, statuses[:2], statuses)
        self.assertEqual(statuses[2], 429, statuses)
        self.assertIn("Retry-After", responses[2].headers)
        self.assertEqual(sales_store.summary()["total"], 0)

    def test_webhooks_get_their_own_budget(self):
        with patch.dict(os.environ, {
            "RATE_LIMIT_ENABLED": "true",
            "RATE_LIMIT_INTAKE_PER_MINUTE": "1",
            "RATE_LIMIT_WEBHOOK_PER_MINUTE": "5",
            "SALES_EMAIL_WEBHOOK_SECRET": "hook-secret",
        }, clear=False):
            intake = [self.client.post("/integrations/leads/website", json={}) for _ in range(2)]
            webhook = [self.client.post("/integrations/email/sales", json={}) for _ in range(2)]
        self.assertEqual(intake[1].status_code, 429, intake[1].text)
        self.assertNotEqual(webhook[0].status_code, 429)
        self.assertNotEqual(webhook[1].status_code, 429, "webhook budget was consumed by intake")

    def test_failed_sign_ins_are_throttled_in_their_own_bucket(self):
        with patch.dict(os.environ, {
            "RATE_LIMIT_ENABLED": "true",
            "RATE_LIMIT_AUTH_FAILURES_PER_MINUTE": "2",
            "DASHBOARD_USER": "founder",
            "DASHBOARD_PASSWORD": "dashboard-secret",
        }, clear=False):
            codes = []
            for _ in range(3):
                response = self.client.get("/company/sales/doctor", auth=("founder", "wrong"))
                codes.append(response.status_code)
            self.assertEqual(codes, [401, 401, 429], codes)
            # Successful sign-ins are unaffected: the bucket counts failures only.
            ok = self.client.get("/company/sales/doctor", auth=("founder", "dashboard-secret"))
            self.assertEqual(ok.status_code, 200, ok.text)

    def test_limiter_can_be_disabled(self):
        with patch.dict(os.environ, {"RATE_LIMIT_ENABLED": "false"}, clear=False):
            responses = [self.client.post("/integrations/leads/website", json={}) for _ in range(5)]
        self.assertNotIn(429, [r.status_code for r in responses])


if __name__ == "__main__":
    unittest.main()
