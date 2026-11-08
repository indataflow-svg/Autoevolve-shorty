"""HTTP wiring for the publisher seam: Buffer default, webhook opt-in."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api import app
from core import marketing_store, sales_store, state
from services.publishers import webhook as webhook_module


class FakeResponse:
    def __init__(self, data: dict, status_code: int = 200):
        self._data = data
        self.status_code = status_code
        self.text = json.dumps(data)

    def json(self) -> dict:
        return self._data


class PublisherApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.old = (state.DB_PATH, marketing_store.DB_PATH, sales_store.DB_PATH)
        state.DB_PATH = marketing_store.DB_PATH = sales_store.DB_PATH = self.root / "company.db"
        state.init_db()
        sales_store.init_sales_db()
        marketing_store.init_marketing_db()
        self.org = state.create_org("Publisher API", "publisher-api")
        state.set_active_org(self.org["id"])
        self.project = patch("app.marketing_api.PROJECTS_ROOT", self.root)
        self.project.start()
        asset_dir = self.root / "post"
        asset_dir.mkdir()
        (asset_dir / "slide.png").write_bytes(b"image-bytes")
        self.post = marketing_store.create_manual_post(
            org_id=self.org["id"],
            platform="instagram",
            post_id="api_publisher_1",
            title="API publisher",
            destination_url="https://example.test/form",
            tracked_url="https://example.test/form?utm_source=instagram",
            source_detail="instagram_carousel",
            asset_dir=str(asset_dir),
            assets=[{"filename": "slide.png", "content_type": "image/png"}],
            metadata={
                "post_type": "carousel",
                "generated_caption": "Caption",
                "publisher": "webhook",
                "publisher_status": "not_started",
                "workflow_status": "ready",
            },
        )
        self.env = patch.dict(os.environ, {
            "DASHBOARD_USER": "founder",
            "DASHBOARD_PASSWORD": "test-secret",
            "SALES_ACTION_TOKEN": "action-secret",
            "SALES_SEND_RECONCILE_ON_STARTUP": "false",
            "PUBLISHER_WEBHOOK_URL": "https://scheduler.example.test/hook",
            "PUBLISHER_WEBHOOK_SECRET": "webhook-secret",
            "PUBLISHER_WEBHOOK_ACCOUNT": "n8n",
            "PUBLIC_BASE_URL": "https://app.test",
        }, clear=False)
        self.env.start()
        self.client = TestClient(app)
        self.auth = ("founder", "test-secret")
        self.headers = {"X-Founder-Action-Token": "action-secret"}

    def tearDown(self):
        self.client.close()
        self.env.stop()
        self.project.stop()
        state.DB_PATH, marketing_store.DB_PATH, sales_store.DB_PATH = self.old
        self.temp.cleanup()

    def test_catalog_and_accounts_expose_webhook_only_when_configured(self):
        catalog = self.client.get("/company/marketing/publishers", auth=self.auth)
        self.assertEqual(catalog.status_code, 200, catalog.text)
        names = [item["name"] for item in catalog.json()["publishers"]]
        self.assertEqual(names[0], "buffer")
        self.assertIn("webhook", names)

        accounts = self.client.get("/company/marketing/publisher-accounts?publisher=webhook", auth=self.auth)
        self.assertEqual(accounts.status_code, 200, accounts.text)
        self.assertEqual(accounts.json()["publisher"], "webhook")
        self.assertEqual(accounts.json()["accounts"][0]["name"], "n8n")

    def test_publish_dispatches_to_the_post_publisher_and_confirm_keeps_provider_verdict(self):
        with patch.object(
            webhook_module.httpx,
            "post",
            side_effect=[
                FakeResponse({"ok": True, "post_id": "ext_api_1", "status": "scheduled"}),
                FakeResponse({"ok": True, "status": "sent", "external_url": "https://social.test/post"}),
            ],
        ):
            response = self.client.post(
                f"/company/marketing/manual-posts/{self.post['id']}/publish",
                auth=self.auth,
                headers=self.headers,
                json={"action": "schedule", "mode": "queue", "account": "n8n"},
            )
            self.assertEqual(response.status_code, 200, response.text)
            body = response.json()
            self.assertEqual(body["post"]["publisher"], "webhook")
            self.assertEqual(body["post"]["publisher_post_ids"], ["ext_api_1"])

            confirmed = self.client.post(
                f"/company/marketing/manual-posts/{self.post['id']}/publish/confirm",
                auth=self.auth,
                headers=self.headers,
                json={},
            )
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        self.assertEqual(confirmed.json()["confirmation"]["overall"], "sent")

    def test_public_asset_link_is_signed_and_works_without_dashboard_auth(self):
        expires = 4_000_000_000
        token = webhook_module.asset_token(self.post["id"], 0, expires)
        response = self.client.get(
            f"/public/manual-posts/{self.post['id']}/assets/0?exp={expires}&token={token}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"image-bytes")
        rejected = self.client.get(
            f"/public/manual-posts/{self.post['id']}/assets/0?exp={expires}&token=wrong"
        )
        self.assertEqual(rejected.status_code, 403)


if __name__ == "__main__":
    unittest.main()
