"""Publisher seam tests: Buffer remains the default, the webhook is opt-in."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import marketing_store, sales_store, state
from services.publishers import PublisherError, catalog, get_publisher
from services.publishers import webhook as webhook_module


class FakeResponse:
    def __init__(self, data: dict, status_code: int = 200):
        self._data = data
        self.status_code = status_code
        self.text = json.dumps(data)

    def json(self) -> dict:
        return self._data


class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.old = (state.DB_PATH, marketing_store.DB_PATH, sales_store.DB_PATH)
        state.DB_PATH = marketing_store.DB_PATH = sales_store.DB_PATH = self.root / "company.db"
        state.init_db()
        sales_store.init_sales_db()
        marketing_store.init_marketing_db()
        self.org = state.create_org("Publisher Test", "publisher-test")
        state.set_active_org(self.org["id"])
        self.asset_root = self.root / "post"
        self.asset_root.mkdir()
        (self.asset_root / "slide.png").write_bytes(b"not-a-real-png")
        self.post = marketing_store.create_manual_post(
            org_id=self.org["id"],
            platform="instagram",
            post_id="publisher_test_1",
            title="Publisher test",
            destination_url="https://example.test/form",
            tracked_url="https://example.test/form?utm_source=instagram",
            source_detail="instagram_carousel",
            asset_dir=str(self.asset_root),
            assets=[{"filename": "slide.png", "content_type": "image/png"}],
            metadata={
                "post_type": "carousel",
                "generated_caption": "A test caption",
                "publisher": "webhook",
                "publisher_status": "not_started",
                "workflow_status": "ready",
            },
        )
        self.env = patch.dict(os.environ, {
            "PUBLISHER_WEBHOOK_URL": "https://scheduler.example.test/hook",
            "PUBLISHER_WEBHOOK_SECRET": "test-secret",
            "PUBLISHER_WEBHOOK_ACCOUNT": "n8n",
            "PUBLIC_BASE_URL": "https://app.example.test/",
        }, clear=False)
        self.env.start()
        self.projects = patch("app.marketing_api.PROJECTS_ROOT", self.root)
        self.projects.start()

    def tearDown(self):
        self.projects.stop()
        self.env.stop()
        state.DB_PATH, marketing_store.DB_PATH, sales_store.DB_PATH = self.old
        self.temp.cleanup()

    def test_buffer_is_default_and_webhook_is_optional(self):
        self.assertEqual(get_publisher().name, "buffer")
        names = [item["name"] for item in catalog()]
        self.assertEqual(names[0], "buffer")
        self.assertIn("webhook", names)
        caps = get_publisher("webhook").capabilities()
        self.assertFalse(caps.draft)
        self.assertTrue(caps.schedule)
        self.assertEqual(get_publisher("webhook").accounts()[0].name, "n8n")

    def test_webhook_schedule_signs_payload_and_persists_generic_metadata(self):
        captured = {}

        def fake_post(url, *, content, headers, timeout):
            captured.update({"url": url, "content": content, "headers": headers, "timeout": timeout})
            return FakeResponse({"ok": True, "post_id": "ext_123", "status": "scheduled"})

        with patch.object(webhook_module.httpx, "post", side_effect=fake_post):
            result = get_publisher("webhook").schedule(
                self.post, account="n8n", mode="timed", due_at="2026-11-01T10:00:00Z"
            )

        self.assertTrue(result["ok"])
        payload = json.loads(captured["content"])
        self.assertEqual(payload["schema"], "company-core.publisher.webhook.v1")
        self.assertEqual(payload["action"], "schedule")
        self.assertEqual(payload["post"]["platform"], "instagram")
        self.assertEqual(payload["schedule"], {"mode": "timed", "due_at": "2026-11-01T10:00:00Z"})
        self.assertEqual(payload["media"][0]["filename"], "slide.png")
        self.assertTrue(payload["media"][0]["url"].startswith("https://app.example.test/public/manual-posts/"))
        expected = "sha256=" + hmac.new(
            b"test-secret", captured["content"], hashlib.sha256
        ).hexdigest()
        self.assertEqual(captured["headers"]["X-Publisher-Signature"], expected)
        self.assertTrue(captured["headers"]["X-Idempotency-Key"].startswith("manual-post:"))

        stored = marketing_store.get_manual_post(self.post["id"])
        metadata = stored["metadata"]
        self.assertEqual(metadata["publisher"], "webhook")
        self.assertEqual(metadata["publisher_status"], "scheduled")
        self.assertEqual(metadata["publisher_post_ids"], ["ext_123"])
        self.assertEqual(metadata["publisher_scheduled_at"], "2026-11-01T10:00:00Z")

    def test_async_publish_job_records_the_provider_result(self):
        from app.marketing_api import _run_publish_job
        from core.jobs_store import create_publish_job, get_publish_job

        def fake_post(url, *, content, headers, timeout):
            return FakeResponse({"ok": True, "post_id": "ext_job", "status": "scheduled"})

        job = create_publish_job(self.org["id"], self.post["id"])
        with patch.object(webhook_module.httpx, "post", side_effect=fake_post):
            _run_publish_job(job["id"], self.post["id"], {"mode": "queue", "account": "n8n"})
        stored = get_publish_job(job["id"], self.org["id"])
        self.assertIsNotNone(stored)
        self.assertEqual(stored["status"], "completed")
        self.assertEqual(stored["result"]["result"]["post_id"], "ext_job")

    def test_webhook_confirm_only_marks_sent_when_provider_says_sent(self):
        metadata = dict(self.post["metadata"])
        metadata["publisher_post_ids"] = ["ext_123"]
        marketing_store.update_manual_post(self.post["id"], metadata_json=json.dumps(metadata))
        post = marketing_store.get_manual_post(self.post["id"])

        with patch.object(
            webhook_module.httpx,
            "post",
            return_value=FakeResponse({"ok": True, "status": "sent", "external_url": "https://social.test/p"}),
        ):
            result = get_publisher("webhook").confirm(post)

        self.assertEqual(result["confirmation"]["overall"], "sent")
        stored = marketing_store.get_manual_post(self.post["id"])
        self.assertEqual(stored["metadata"]["publisher_send_confirmation"]["overall"], "sent")

    def test_signed_asset_link_rejects_bad_tokens_and_returns_the_file(self):
        expires = 4_000_000_000
        token = webhook_module.asset_token(self.post["id"], 0, expires)
        path, filename, content_type = webhook_module.public_asset(self.post["id"], 0, expires, token)
        self.assertEqual(path, self.asset_root / "slide.png")
        self.assertEqual(filename, "slide.png")
        self.assertEqual(content_type, "image/png")
        with self.assertRaises(PublisherError):
            webhook_module.public_asset(self.post["id"], 0, expires, "wrong")

    def test_unconfigured_webhook_is_not_offered(self):
        with patch.dict(os.environ, {"PUBLISHER_WEBHOOK_URL": "", "PUBLISHER_WEBHOOK_SECRET": ""}, clear=False):
            names = [item["name"] for item in catalog()]
            self.assertNotIn("webhook", names)
            with self.assertRaises(PublisherError):
                get_publisher("webhook").schedule(self.post)


if __name__ == "__main__":
    unittest.main()
