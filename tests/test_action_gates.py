import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api import app
import core.marketing_store as marketing_store
import core.sales_store as sales_store
import core.state as state


GATED_ROUTES = [
    # P0-2: setup wizard write
    "/company/setup/step",
    # P0-2: coding agent spends model budget / mutates a workspace
    "/company/coding/tasks",
    "/company/coding/tasks/task_1/apply",
    # P0-2: monitor may run shell diagnostics and auto-repair
    "/company/monitor/run",
    "/company/monitor/run/api",
    # P0-2: marketing approvals and external publishing
    "/company/marketing/campaigns/camp_1/variants/var_1/select",
    "/company/marketing/campaigns/camp_1/drafts",
    "/company/marketing/campaigns/camp_1/approve-script",
    "/company/marketing/campaigns/camp_1/regenerate-script",
    "/company/marketing/campaigns/camp_1/retry",
    "/company/marketing/manual-posts/post_1/buffer-schedule",
]


class ActionGateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        database = Path(self.temporary.name) / "company.db"
        self.original = (state.DB_PATH, sales_store.DB_PATH, marketing_store.DB_PATH)
        state.DB_PATH = database
        sales_store.DB_PATH = database
        marketing_store.DB_PATH = database
        state.init_db()
        sales_store.init_sales_db()
        marketing_store.init_marketing_db()
        self.client = TestClient(app)
        self.auth = ("founder", "dashboard-secret")
        self.headers = {"X-Founder-Action-Token": "action-secret"}
        self.env = patch.dict(os.environ, {
            "DASHBOARD_USER": "founder",
            "DASHBOARD_PASSWORD": "dashboard-secret",
            "SALES_ACTION_TOKEN": "action-secret",
        }, clear=False)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        state.DB_PATH, sales_store.DB_PATH, marketing_store.DB_PATH = self.original
        self.temporary.cleanup()

    def test_mutating_routes_reject_requests_without_the_action_token(self):
        for path in GATED_ROUTES:
            with self.subTest(path=path):
                response = self.client.post(path, auth=self.auth, json={})
                self.assertEqual(response.status_code, 403, f"{path}: {response.text}")

    def test_setup_step_write_accepts_the_action_token(self):
        denied = self.client.post("/company/setup/step", auth=self.auth, json={"step": "4"})
        self.assertEqual(denied.status_code, 403)
        allowed = self.client.post(
            "/company/setup/step", auth=self.auth, headers=self.headers, json={"step": "3"}
        )
        self.assertEqual(allowed.status_code, 200, allowed.text)
        self.assertEqual(allowed.json()["step"], "3")

    def test_setup_step_write_requires_dashboard_auth(self):
        response = self.client.post("/company/setup/step", json={"step": "3"})
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
