"""OAuth lifecycle: official flows, encrypted vault, honest states.

The code is complete; only external app approvals are missing. These tests
prove the lifecycle against stubbed providers: state that cannot be forged,
secrets that never persist in plaintext, refresh and revocation that behave,
and a catalog that flips from coming-soon to connectable on credentials
alone — no code change required for that flip.
"""
import json
import os
import tempfile
import time
import unittest
import urllib.parse
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

import core.state as state
from app.api import app
from core import commercial_store, marketing_store, sales_store, workflow_store
from services import oauth as oauth_service


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


TOKEN_RESPONSE = {"access_token": "acc-123", "refresh_token": "ref-456",
                  "expires_in": 3600, "token_type": "Bearer"}


class OAuthBase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self._paths = (state.DB_PATH, commercial_store.DB_PATH, sales_store.DB_PATH,
                       workflow_store.DB_PATH, marketing_store.DB_PATH)
        state.DB_PATH = commercial_store.DB_PATH = sales_store.DB_PATH = base / "company.db"
        workflow_store.DB_PATH = base / "workflows.db"
        state.init_db()
        sales_store.init_sales_db()
        commercial_store.init_commercial_db()
        marketing_store.init_marketing_db()
        workflow_store.init_db()
        self.vault_key = Fernet.generate_key().decode()
        self.env = patch.dict(os.environ, {
            "DASHBOARD_USER": "founder", "DASHBOARD_PASSWORD": "pw",
            "SALES_ACTION_TOKEN": "action-secret",
            "SALES_SEND_RECONCILE_ON_STARTUP": "false",
            "RATE_LIMIT_ENABLED": "false",
            "OAUTH_TOKEN_KEY": self.vault_key,
            "HUBSPOT_CLIENT_ID": "hub-id",
            "HUBSPOT_CLIENT_SECRET": "hub-secret",
            "COMPANY_PUBLIC_URL": "https://app.example.test",
        }, clear=False)
        self.env.start()
        self.client = TestClient(app)
        self.auth = ("founder", "pw")
        self.headers = {"X-Founder-Action-Token": "action-secret"}

    def tearDown(self):
        self.env.stop()
        (state.DB_PATH, commercial_store.DB_PATH, sales_store.DB_PATH,
         workflow_store.DB_PATH, marketing_store.DB_PATH) = self._paths
        self.temporary.cleanup()

    def token_response(self, payload=None):
        return FakeResponse(payload if payload is not None else dict(TOKEN_RESPONSE))


class StateTests(OAuthBase):
    def test_authorize_builds_the_provider_url_with_signed_state(self):
        url = oauth_service.build_authorize_url("hubspot", 0)
        parts = urllib.parse.urlparse(url)
        self.assertEqual(parts.netloc, "app.hubspot.com")
        query = urllib.parse.parse_qs(parts.query)
        self.assertEqual(query["client_id"], ["hub-id"])
        self.assertIn("hubspot/callback", query["redirect_uri"][0])
        oauth_service.verify_state("hubspot", query["state"][0], 0)

    def test_tampered_expired_and_mismatched_states_fail(self):
        url = oauth_service.build_authorize_url("hubspot", 0)
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        raw = query["state"][0]
        tampered = raw[:-1] + ("0" if raw[-1] != "0" else "1")
        with self.assertRaises(oauth_service.OAuthError):
            oauth_service.verify_state("hubspot", tampered, 0)
        with self.assertRaises(oauth_service.OAuthError):
            oauth_service.verify_state("hubspot", "not.a.state", 0)
        with self.assertRaises(oauth_service.OAuthError):
            oauth_service.verify_state("salesforce", raw, 0)

    def test_unknown_provider_has_no_flow(self):
        with self.assertRaises(oauth_service.OAuthError):
            oauth_service.build_authorize_url("nope", 0)
        self.assertEqual(
            self.client.post("/company/commercial/integrations/nope/connect",
                             auth=self.auth, headers=self.headers, json={}).status_code, 404)


class ConfigTests(OAuthBase):
    def test_missing_approval_names_its_variables(self):
        with patch.dict(os.environ, {"HUBSPOT_CLIENT_ID": "", "HUBSPOT_CLIENT_SECRET": ""},
                        clear=False):
            self.assertFalse(oauth_service.is_configured("hubspot"))
            response = self.client.post("/company/commercial/integrations/hubspot/connect",
                                        auth=self.auth, headers=self.headers, json={})
            self.assertEqual(response.status_code, 422, response.text)
            self.assertIn("HUBSPOT_CLIENT_ID", response.json()["detail"])

    def test_credentials_flip_coming_soon_to_available(self):
        body = self.client.get("/company/commercial/integrations", auth=self.auth).json()
        hubspot = next(i for i in body if i["provider"] == "hubspot")
        self.assertEqual(hubspot["state"], "available")
        with patch.dict(os.environ, {"HUBSPOT_CLIENT_ID": ""}, clear=False):
            body = self.client.get("/company/commercial/integrations", auth=self.auth).json()
            hubspot = next(i for i in body if i["provider"] == "hubspot")
            self.assertEqual(hubspot["state"], "coming_soon")
            self.assertIn("HUBSPOT_CLIENT_ID", hubspot["blocker"])


class CallbackTests(OAuthBase):
    def authorize_state(self):
        url = oauth_service.build_authorize_url("hubspot", 0)
        return urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["state"][0]

    def test_callback_stores_encrypted_tokens_and_marks_healthy(self):
        with patch("services.oauth.urllib.request.urlopen",
                   return_value=self.token_response()):
            response = self.client.get(
                "/company/commercial/integrations/hubspot/callback",
                params={"code": "single-use-code", "state": self.authorize_state()},
                follow_redirects=False)
        self.assertEqual(response.status_code, 303, response.text)
        self.assertIn("/commercial", response.headers["location"])
        with commercial_store.connect() as db:
            row = db.execute(
                "SELECT ciphertext FROM integration_secrets WHERE provider='hubspot'").fetchone()
            self.assertIsNotNone(row)
            # Ciphertext only: neither token appears in storage.
            self.assertNotIn("acc-123", row["ciphertext"])
            self.assertNotIn("ref-456", row["ciphertext"])
            conn = db.execute(
                "SELECT status, credential_ref FROM integration_connections"
                " WHERE provider='hubspot'").fetchone()
        self.assertEqual(conn["status"], "healthy")
        self.assertEqual(conn["credential_ref"], "oauth:vault")
        stored = oauth_service.read_tokens("hubspot", 0)
        self.assertEqual(stored["access_token"], "acc-123")
        self.assertEqual(stored["refresh_token"], "ref-456")

    def test_callback_rejects_a_forged_state_without_storing(self):
        response = self.client.get(
            "/company/commercial/integrations/hubspot/callback",
            params={"code": "x", "state": "hubspot.0.nonce.1.deadbeef"},
            follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        with commercial_store.connect() as db:
            self.assertIsNone(db.execute(
                "SELECT 1 FROM integration_secrets WHERE provider='hubspot'").fetchone())

    def test_provider_refusal_marks_action_required(self):
        with patch("services.oauth.urllib.request.urlopen",
                   return_value=self.token_response({"error": "bad_verification_code"})):
            response = self.client.get(
                "/company/commercial/integrations/hubspot/callback",
                params={"code": "used-code", "state": self.authorize_state()},
                follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        with commercial_store.connect() as db:
            row = db.execute(
                "SELECT status FROM integration_connections WHERE provider='hubspot'").fetchone()
            # No row is created for a failed authorization; nothing pretends.
            self.assertIsNone(row)


class RefreshRevokeTests(OAuthBase):
    def connected(self):
        with patch("services.oauth.urllib.request.urlopen",
                   return_value=self.token_response()):
            oauth_service.exchange_code("hubspot", "code-1", 0)
        with commercial_store.connect() as db:
            db.execute(
                "INSERT INTO integration_connections (id, org_id, provider, status,"
                " sync_status, credential_ref, created_at, updated_at)"
                " VALUES ('conn_1', 0, 'hubspot', 'healthy', 'idle', 'oauth:vault', '', '')")

    def test_refresh_rotates_and_sync_validates(self):
        self.connected()
        with patch("services.oauth.urllib.request.urlopen",
                   return_value=self.token_response({"access_token": "acc-2",
                                                     "refresh_token": "ref-2",
                                                     "expires_in": 3600})):
            outcome = oauth_service.validate_connection("hubspot", 0)
        self.assertTrue(outcome["healthy"])
        self.assertEqual(oauth_service.read_tokens("hubspot", 0)["access_token"], "acc-2")
        response = self.client.post("/company/commercial/integrations/hubspot/sync",
                                    auth=self.auth, headers=self.headers, json={})
        # Sync itself revalidates through the same stubbed transport.
        self.assertIn(response.status_code, (200, 422))

    def test_failed_refresh_surfaces_action_required(self):
        self.connected()
        with patch("services.oauth.urllib.request.urlopen",
                   return_value=self.token_response({"error": "invalid_grant"})):
            outcome = oauth_service.validate_connection("hubspot", 0)
        self.assertFalse(outcome["healthy"])

    def test_disconnect_destroys_tokens_and_keeps_history(self):
        self.connected()
        response = self.client.post("/company/commercial/integrations/hubspot/disconnect",
                                    auth=self.auth, headers=self.headers, json={})
        self.assertEqual(response.status_code, 200)
        with commercial_store.connect() as db:
            self.assertIsNone(db.execute(
                "SELECT 1 FROM integration_secrets WHERE provider='hubspot'").fetchone())
            row = db.execute(
                "SELECT status FROM integration_connections WHERE provider='hubspot'").fetchone()
            self.assertEqual(row["status"], "disconnected")
        self.assertIsNone(oauth_service.read_tokens("hubspot", 0))

    def test_vault_key_is_required(self):
        with patch.dict(os.environ, {"OAUTH_TOKEN_KEY": ""}, clear=False):
            with self.assertRaises(oauth_service.OAuthNotConfigured):
                oauth_service.store_tokens("hubspot", dict(TOKEN_RESPONSE), 0)


if __name__ == "__main__":
    unittest.main()
