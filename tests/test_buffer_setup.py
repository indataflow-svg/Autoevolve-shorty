import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api import app
from services import buffer_setup


class FakeBufferClient:
    """Stand-in for engines.g3.g3_runtime.buffer.BufferClient."""

    def __init__(self, token: str):
        self.token = token

    def account(self):
        return {
            "id": "acct_1",
            "email": "owner@example.com",
            "organizations": [{"id": "org_1", "name": "Acme"}],
        }

    def channels(self, organization_id: str):
        if organization_id != "org_1":
            return []
        return [
            {
                "id": "ch_ig", "name": "acme", "displayName": "Acme IG",
                "descriptor": "Instagram Business", "service": "instagram",
                "type": "business", "isDisconnected": False, "isLocked": False,
            },
            {
                "id": "ch_x", "name": "acme", "displayName": "Acme X",
                "descriptor": "X profile", "service": "twitter",
                "type": "profile", "isDisconnected": False, "isLocked": False,
            },
            {
                "id": "ch_li", "name": "acme", "displayName": "Acme LinkedIn",
                "descriptor": "LinkedIn page", "service": "linkedin",
                "type": "page", "isDisconnected": False, "isLocked": False,
            },
            {
                "id": "ch_locked", "name": "acme", "displayName": "Locked IG",
                "descriptor": "", "service": "instagram",
                "type": "business", "isDisconnected": False, "isLocked": True,
            },
        ]


class BufferSetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.g3_file = Path(self.tmp.name) / "g3.env"
        self.g3_file.write_text("BUFFER_API_KEY=\n")
        self.env = {
            "SETUP_G3_ENV_FILE": str(self.g3_file),
            "BUFFER_ENDPOINT": "https://api.buffer.com",
            "DASHBOARD_USER": "u",
            "DASHBOARD_PASSWORD": "p",
            "SALES_ACTION_TOKEN": "founder-token",
        }
        self.patch_env = patch.dict(os.environ, self.env, clear=False)
        self.patch_env.start()
        for key in ("BUFFER_API_KEY", "BUFFER_ORGANIZATION_ID", "BUFFER_INSTAGRAM_CHANNEL_ID",
                    "BUFFER_X_CHANNEL_ID", "BUFFER_LINKEDIN_CHANNEL_ID",
                    "BUFFER_ACME_API_KEY", "BUFFER_ACME_ORGANIZATION_ID",
                    "BUFFER_ACME_INSTAGRAM_CHANNEL_ID", "BUFFER_ACME_X_CHANNEL_ID",
                    "BUFFER_ACME_LINKEDIN_CHANNEL_ID"):
            os.environ.pop(key, None)

    def tearDown(self):
        self.patch_env.stop()
        self.tmp.cleanup()

    def _factory(self, token: str):
        self.assertIsInstance(token, str)
        return FakeBufferClient(token)

    def test_discover_marks_supported_and_usable_channels_without_leaking_the_key(self):
        self.g3_file.write_text("BUFFER_API_KEY=saved-token-123\n")
        result = buffer_setup.discover("default", client_factory=self._factory)
        self.assertEqual(result["account"], "default")
        self.assertEqual([org["id"] for org in result["organizations"]], ["org_1"])
        channels = {channel["id"]: channel for channel in result["organizations"][0]["channels"]}
        self.assertEqual(channels["ch_ig"]["platform"], "instagram")
        self.assertTrue(channels["ch_ig"]["supported"])
        self.assertTrue(channels["ch_ig"]["usable"])
        self.assertEqual(channels["ch_x"]["platform"], "x")
        self.assertEqual(channels["ch_li"]["platform"], "linkedin")
        self.assertTrue(channels["ch_li"]["supported"])
        self.assertTrue(channels["ch_li"]["usable"])
        self.assertFalse(channels["ch_locked"]["usable"])
        self.assertNotIn("saved-token-123", json.dumps(result))

    def test_discover_uses_the_saved_key_for_a_named_account(self):
        self.g3_file.write_text("BUFFER_ACME_API_KEY=named-token-123\n")
        seen = []

        def factory(token):
            seen.append(token)
            return FakeBufferClient(token)

        buffer_setup.discover("acme", client_factory=factory)
        self.assertEqual(seen, ["named-token-123"])

    def test_discover_requires_a_key_when_none_is_saved(self):
        with self.assertRaisesRegex(ValueError, "no saved API key"):
            buffer_setup.discover("missing", client_factory=self._factory)

    def test_bind_writes_prefixed_keys_and_clears_unselected_platform(self):
        result = buffer_setup.bind(
            "acme",
            api_key="token-12345678",
            organization_id="org_1",
            instagram_channel_id="ch_ig",
            x_channel_id=None,
            linkedin_channel_id="ch_li",
            client_factory=self._factory,
        )
        self.assertTrue(result["ok"])
        self.assertFalse(result["restart_required"])
        values = buffer_setup.read_values(self.g3_file)
        self.assertEqual(values["BUFFER_ACME_API_KEY"], "token-12345678")
        self.assertEqual(values["BUFFER_ACME_ORGANIZATION_ID"], "org_1")
        self.assertEqual(values["BUFFER_ACME_INSTAGRAM_CHANNEL_ID"], "ch_ig")
        self.assertEqual(values["BUFFER_ACME_X_CHANNEL_ID"], "")
        self.assertEqual(values["BUFFER_ACME_LINKEDIN_CHANNEL_ID"], "ch_li")
        self.assertEqual(os.environ["BUFFER_ACME_INSTAGRAM_CHANNEL_ID"], "ch_ig")
        self.assertEqual(os.environ["BUFFER_ACME_LINKEDIN_CHANNEL_ID"], "ch_li")
        self.assertNotIn("Unsupported services", " ".join(result["warnings"]))
        self.assertNotIn("token-12345678", json.dumps(result))

    def test_bind_with_no_channels_warns_that_scheduling_is_impossible(self):
        result = buffer_setup.bind(
            "acme",
            api_key="token-12345678",
            organization_id="org_1",
            client_factory=self._factory,
        )
        self.assertTrue(result["ok"])
        self.assertIn("LinkedIn", " ".join(result["warnings"]))

    def test_bind_rejects_a_channel_from_the_wrong_platform(self):
        with self.assertRaisesRegex(ValueError, "not x"):
            buffer_setup.bind(
                "acme", api_key="token-12345678", organization_id="org_1",
                instagram_channel_id=None, x_channel_id="ch_ig",
                client_factory=self._factory,
            )
        with self.assertRaisesRegex(ValueError, "not linkedin"):
            buffer_setup.bind(
                "acme", api_key="token-12345678", organization_id="org_1",
                linkedin_channel_id="ch_x",
                client_factory=self._factory,
            )

    def test_bind_rejects_unknown_or_locked_channels_and_other_orgs(self):
        with self.assertRaisesRegex(ValueError, "not a usable channel"):
            buffer_setup.bind(
                "acme", api_key="token-12345678", organization_id="org_1",
                instagram_channel_id="ch_locked", client_factory=self._factory,
            )
        with self.assertRaisesRegex(ValueError, "does not belong"):
            buffer_setup.bind(
                "acme", api_key="token-12345678", organization_id="org_other",
                instagram_channel_id="ch_ig", client_factory=self._factory,
            )

    def test_list_accounts_reports_masked_state(self):
        self.g3_file.write_text(
            "BUFFER_API_KEY=default-token-123\n"
            "BUFFER_ACME_API_KEY=acme-token-123\n"
            "BUFFER_ACME_ORGANIZATION_ID=org_1\n"
            "BUFFER_ACME_INSTAGRAM_CHANNEL_ID=ch_ig\n"
        )
        accounts = {item["name"]: item for item in buffer_setup.list_accounts()}
        self.assertEqual(set(accounts), {"acme", "default"})
        self.assertTrue(accounts["acme"]["api_key_present"])
        self.assertEqual(accounts["acme"]["organization_id"], "org_1")
        self.assertEqual(accounts["acme"]["instagram_channel_id"], "ch_ig")
        self.assertIsNone(accounts["acme"]["x_channel_id"])
        self.assertNotIn("acme-token-123", json.dumps(accounts))

    def test_integrations_view_reports_named_accounts_without_the_key(self):
        self.g3_file.write_text(
            "BUFFER_ACME_API_KEY=acme-token-123\n"
            "BUFFER_ACME_ORGANIZATION_ID=org_1\n"
            "BUFFER_ACME_INSTAGRAM_CHANNEL_ID=ch_ig\n"
        )
        response = TestClient(app).get("/company/ui/integrations", auth=("u", "p"))
        self.assertEqual(response.status_code, 200, response.text)
        social = next(group for group in response.json()["groups"] if group["id"] == "social")
        self.assertEqual(
            social["accounts"],
            [{
                "name": "acme",
                "api_key_present": True,
                "organization_id": "org_1",
                "channels": ["instagram"],
            }],
        )
        self.assertNotIn("acme-token-123", response.text)

    def test_routes_require_the_founder_token_and_return_discovery(self):
        self.g3_file.write_text("BUFFER_API_KEY=saved-token-123\n")
        client = TestClient(app)
        auth = ("u", "p")
        missing = client.post("/company/setup/buffer/discover", auth=auth, json={"account": "default"})
        self.assertEqual(missing.status_code, 403)

        with patch("services.buffer_setup._default_client", side_effect=self._factory):
            found = client.post(
                "/company/setup/buffer/discover",
                auth=auth,
                headers={"X-Founder-Action-Token": "founder-token"},
                json={"account": "default"},
            )
        self.assertEqual(found.status_code, 200, found.text)
        body = found.json()
        self.assertEqual(body["organizations"][0]["id"], "org_1")
        self.assertNotIn("saved-token-123", found.text)

        accounts = client.get("/company/setup/buffer/accounts", auth=auth)
        self.assertEqual(accounts.status_code, 200, accounts.text)
        self.assertTrue(accounts.json()["accounts"][0]["api_key_present"])
        self.assertNotIn("saved-token-123", accounts.text)

    def test_connect_route_writes_the_account_and_returns_no_token(self):
        self.g3_file.write_text("BUFFER_ACME_API_KEY=\n")
        client = TestClient(app)
        with patch("services.buffer_setup._default_client", side_effect=self._factory):
            saved = client.post(
                "/company/setup/buffer/connect",
                auth=("u", "p"),
                headers={"X-Founder-Action-Token": "founder-token"},
                json={
                    "account": "acme",
                    "api_key": "token-12345678",
                    "organization_id": "org_1",
                    "instagram_channel_id": "ch_ig",
                    "x_channel_id": "ch_x",
                },
            )
        self.assertEqual(saved.status_code, 200, saved.text)
        body = saved.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["instagram_channel_id"], "ch_ig")
        self.assertEqual(body["x_channel_id"], "ch_x")
        self.assertFalse(body["restart_required"])
        self.assertNotIn("token-12345678", saved.text)
        values = buffer_setup.read_values(self.g3_file)
        self.assertEqual(values["BUFFER_ACME_API_KEY"], "token-12345678")
        self.assertEqual(values["BUFFER_ACME_X_CHANNEL_ID"], "ch_x")


if __name__ == "__main__":
    unittest.main()
