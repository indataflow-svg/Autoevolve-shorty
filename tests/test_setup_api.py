import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class SetupKeysTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env_file = Path(self.tmp.name) / ".env"
        self.g3_file = Path(self.tmp.name) / "g3.env"
        self.env_file.write_text("OMNIROUTE_BASE_URL=http://127.0.0.1:20128/v1\nOMNIROUTE_API_KEY=\n")
        self.g3_file.write_text("BUFFER_API_KEY=\n")
        self.patch_env = patch.dict(os.environ, {
            "SETUP_ENV_FILE": str(self.env_file),
            "SETUP_G3_ENV_FILE": str(self.g3_file),
        }, clear=False)
        self.patch_env.start()

    def tearDown(self):
        self.patch_env.stop()
        self.tmp.cleanup()

    def test_group_status_masks_values(self):
        from core.setup_keys import group_status

        status = group_status()
        ai = status["ai_gateway"]
        self.assertIn("OMNIROUTE_BASE_URL", ai["configured"])
        self.assertIn("OMNIROUTE_API_KEY", ai["missing"])
        self.assertNotIn("http://127.0.0.1:20128/v1", str(status))

    def test_validate_rejects_unknown_group(self):
        from core.setup_keys import validate_group

        result = validate_group("nope", {})
        self.assertFalse(result["ok"])

    def test_validate_rejects_mismatched_sender(self):
        from core.setup_keys import validate_group

        result = validate_group("email", {
            "SALES_FROM_EMAIL": "sales@other.com",
            "SALES_RESEND_DOMAIN": "verified.com",
        })
        self.assertFalse(result["ok"])
        self.assertIn("SALES_FROM_EMAIL", result["errors"])

    def test_save_writes_and_backs_up(self):
        from core.setup_keys import save_group

        result = save_group("prospecting", {"HUNTER_API_KEY": "hunter-secret-value"})
        self.assertTrue(result["ok"], result)
        self.assertIn("HUNTER_API_KEY", result["saved"])
        self.assertTrue(result["backup"])
        content = self.env_file.read_text()
        self.assertIn("HUNTER_API_KEY=hunter-secret-value", content)
        backups = list(Path(self.tmp.name).glob(".env.*.bak"))
        self.assertTrue(backups)

    def test_save_rejects_bad_values_without_touching_file(self):
        from core.setup_keys import save_group

        before = self.env_file.read_bytes()
        result = save_group("prospecting", {"HUNTER_API_KEY": "has space"})
        self.assertFalse(result["ok"])
        self.assertEqual(self.env_file.read_bytes(), before)

    def test_save_rejects_unknown_keys(self):
        from core.setup_keys import save_group

        result = save_group("prospecting", {"EVIL_KEY": "x" * 20})
        self.assertTrue(result["ok"])
        self.assertNotIn("EVIL_KEY", result.get("saved", []))
        self.assertNotIn("EVIL_KEY", self.env_file.read_text())

    def test_router_endpoints(self):
        import core.sales_store as sales_store
        import core.state as state
        from app.api import app
        from fastapi.testclient import TestClient

        db_tmp = tempfile.TemporaryDirectory()
        database = Path(db_tmp.name) / "company.db"
        old_state, old_sales = state.DB_PATH, sales_store.DB_PATH
        state.DB_PATH = database
        sales_store.DB_PATH = database
        try:
            state.init_db()
            sales_store.init_sales_db()
            client = TestClient(app)
            with patch.dict(os.environ, {
                "DASHBOARD_USER": "founder",
                "DASHBOARD_PASSWORD": "dashboard-secret",
                "SALES_ACTION_TOKEN": "action-secret",
            }, clear=False):
                auth = ("founder", "dashboard-secret")
                headers = {"X-Founder-Action-Token": "action-secret"}
                response = client.get("/company/setup/providers", auth=auth)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(any(g["id"] == "ai_gateway" for g in response.json()["groups"]))
                # Writes require the founder token.
                denied = client.post("/company/setup/keys/test", auth=auth,
                                     json={"group": "prospecting", "values": {}})
                self.assertEqual(denied.status_code, 403)
                ok = client.post("/company/setup/keys/test", auth=auth, headers=headers,
                                 json={"group": "prospecting", "values": {"HUNTER_API_KEY": "hunter-secret-value"}})
                self.assertEqual(ok.status_code, 200)
                saved = client.post("/company/setup/keys", auth=auth, headers=headers,
                                    json={"group": "prospecting", "values": {"HUNTER_API_KEY": "hunter-secret-value"}})
                self.assertEqual(saved.status_code, 200)
                self.assertTrue(saved.json()["restart_required"])
                unknown = client.post("/company/setup/keys", auth=auth, headers=headers,
                                      json={"group": "nope", "values": {}})
                self.assertEqual(unknown.status_code, 422)
        finally:
            state.DB_PATH = old_state
            sales_store.DB_PATH = old_sales
            db_tmp.cleanup()
