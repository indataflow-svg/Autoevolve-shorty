import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api import app
import core.marketing_store as marketing_store
import core.state as state


SCHEDULED_OUTPUT = json.dumps({
    "ok": True, "campaign_id": "camp_1", "provider": "buffer", "scheduled": True,
    "mode": "queue", "results": [{"platform": "x", "status": "scheduled", "post_id": "post-9"}],
})


def _config():
    return SimpleNamespace(g3_bin=Path("/bin/true"), g3_root=Path("/tmp"),
                           g3_env_file=None, stage_timeout=60)


class BufferScheduleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary.name) / "company.db"
        self.old_state_path = state.DB_PATH
        self.old_marketing_path = marketing_store.DB_PATH
        state.DB_PATH = self.database
        marketing_store.DB_PATH = self.database
        state.init_db()
        marketing_store.init_marketing_db()
        self.project = state.create_org("Example Company", "company-core", env_prefix="BUFFER_")
        state.set_active_org(self.project["id"])
        self.client = TestClient(app)
        self.auth = ("founder", "dashboard-secret")
        self.env = patch.dict(os.environ, {
            "DASHBOARD_USER": "founder",
            "DASHBOARD_PASSWORD": "dashboard-secret",
        }, clear=False)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        state.DB_PATH = self.old_state_path
        marketing_store.DB_PATH = self.old_marketing_path
        self.temporary.cleanup()

    def _post(self, **metadata):
        base = {"workflow_status": "ready"}
        base.update(metadata)
        return marketing_store.create_manual_post(
            org_id=self.project["id"], platform="x", post_id="x_post_1",
            destination_url="https://example.com", tracked_url="https://example.com/?x=1",
            asset_dir=str(Path(self.temporary.name)), assets=[], metadata=base)

    def _schedule(self, post_id, payload):
        return self.client.post(f"/company/marketing/manual-posts/{post_id}/buffer-schedule",
                                auth=self.auth, json=payload)

    def test_queue_schedule_marks_post_scheduled(self):
        post = self._post()
        with patch("app.marketing_api.MarketingConfig.load", return_value=_config()), \
                patch("app.marketing_api._manual_post_handoff",
                      return_value=(Path("/tmp/handoff.json"), Path(self.temporary.name))), \
                patch("app.marketing_api._run", return_value=SCHEDULED_OUTPUT) as run_mock:
            response = self._schedule(post["id"], {"mode": "queue"})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["post"]["buffer_status"], "scheduled")
        self.assertIn("queue", body["message"])
        command = run_mock.call_args[0][0]
        self.assertIn("schedule", command)
        self.assertIn("queue", command)
        self.assertNotIn("--due-at", command)

    def test_timed_schedule_passes_due_at_and_records_it(self):
        post = self._post()
        with patch("app.marketing_api.MarketingConfig.load", return_value=_config()), \
                patch("app.marketing_api._manual_post_handoff",
                      return_value=(Path("/tmp/handoff.json"), Path(self.temporary.name))), \
                patch("app.marketing_api._run", return_value=SCHEDULED_OUTPUT) as run_mock:
            response = self._schedule(post["id"], {"mode": "timed", "due_at": "2999-01-02T10:00:00Z"})
        self.assertEqual(response.status_code, 200, response.text)
        command = run_mock.call_args[0][0]
        self.assertIn("--due-at", command)
        stored = marketing_store.get_manual_post(post["id"])
        metadata = stored["metadata"]
        self.assertEqual(metadata["buffer_status"], "scheduled")
        self.assertEqual(metadata["buffer_schedule_mode"], "timed")
        self.assertEqual(metadata["buffer_scheduled_at"], "2999-01-02T10:00:00Z")
        self.assertEqual(metadata["buffer_post_ids"], ["post-9"])

    def test_timed_without_due_at_is_rejected(self):
        post = self._post()
        response = self._schedule(post["id"], {"mode": "timed"})
        self.assertEqual(response.status_code, 422)

    def test_unknown_mode_is_rejected(self):
        post = self._post()
        response = self._schedule(post["id"], {"mode": "now"})
        self.assertEqual(response.status_code, 422)

    def test_unready_post_is_rejected(self):
        post = self._post(workflow_status="uploading")
        response = self._schedule(post["id"], {"mode": "queue"})
        self.assertEqual(response.status_code, 409)

    def test_concurrent_run_is_rejected(self):
        post = self._post(buffer_status="running")
        response = self._schedule(post["id"], {"mode": "queue"})
        self.assertEqual(response.status_code, 409)

    def test_backend_failure_marks_post_failed(self):
        post = self._post()
        with patch("app.marketing_api.MarketingConfig.load", return_value=_config()), \
                patch("app.marketing_api._manual_post_handoff",
                      return_value=(Path("/tmp/handoff.json"), Path(self.temporary.name))), \
                patch("app.marketing_api._run", side_effect=RuntimeError("boom")):
            response = self._schedule(post["id"], {"mode": "queue"})
        self.assertEqual(response.status_code, 502)
        stored = marketing_store.get_manual_post(post["id"])
        self.assertEqual(stored["metadata"]["buffer_status"], "failed")

    def test_named_account_passes_through_to_g3(self):
        post = self._post()
        with patch("app.marketing_api.MarketingConfig.load", return_value=_config()), \
                patch("app.marketing_api._manual_post_handoff",
                      return_value=(Path("/tmp/handoff.json"), Path(self.temporary.name))), \
                patch("app.marketing_api._run", return_value=SCHEDULED_OUTPUT) as run_mock:
            response = self.client.post(
                f"/company/marketing/manual-posts/{post['id']}/buffer-schedule?buffer_account=beta",
                auth=self.auth, json={"mode": "queue"})
        self.assertEqual(response.status_code, 200, response.text)
        command = run_mock.call_args[0][0]
        self.assertIn("--account", command)
        self.assertIn("beta", command)
        stored = marketing_store.get_manual_post(post["id"])
        self.assertEqual(stored["metadata"]["buffer_account"], "beta")

    def test_invalid_account_name_is_rejected(self):
        post = self._post()
        response = self.client.post(
            f"/company/marketing/manual-posts/{post['id']}/buffer-schedule?buffer_account=BAD+NAME!",
            auth=self.auth, json={"mode": "queue"})
        self.assertEqual(response.status_code, 422)

    def test_draft_fans_out_to_two_accounts(self):
        post = self._post()
        with patch("app.marketing_api.MarketingConfig.load", return_value=_config()), \
                patch("app.marketing_api._manual_post_handoff",
                      return_value=(Path("/tmp/handoff.json"), Path(self.temporary.name))), \
                patch("app.marketing_api._run", return_value=SCHEDULED_OUTPUT) as run_mock:
            response = self.client.post(
                f"/company/marketing/manual-posts/{post['id']}/buffer-draft?buffer_account=default,beta",
                auth=self.auth)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(run_mock.call_count, 2)
        commands = [call.args[0] for call in run_mock.call_args_list]
        self.assertTrue(any("beta" in command for command in commands))
        stored = marketing_store.get_manual_post(post["id"])
        self.assertEqual(stored["metadata"]["buffer_accounts"], ["default", "beta"])
        self.assertEqual(stored["metadata"]["buffer_status"], "drafted")

    def test_partial_schedule_failure_keeps_successes(self):
        post = self._post()
        calls = {"n": 0}

        def flaky(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("boom")
            return SCHEDULED_OUTPUT

        with patch("app.marketing_api.MarketingConfig.load", return_value=_config()), \
                patch("app.marketing_api._manual_post_handoff",
                      return_value=(Path("/tmp/handoff.json"), Path(self.temporary.name))), \
                patch("app.marketing_api._run", side_effect=flaky):
            multi = self.client.post(
                f"/company/marketing/manual-posts/{post['id']}/buffer-schedule?buffer_account=beta,default",
                auth=self.auth, json={"mode": "queue"})
        self.assertEqual(multi.status_code, 200, multi.text)
        stored = marketing_store.get_manual_post(post["id"])
        self.assertEqual(stored["metadata"]["buffer_status"], "scheduled")
        self.assertEqual(stored["metadata"]["buffer_accounts"], ["beta", "default"])
        self.assertIn("beta", stored["metadata"].get("buffer_error", ""))

    def test_buffer_accounts_lists_configured_accounts(self):
        payload = json.dumps({"ok": True, "accounts": [
            {"name": "default", "organization_id": "org-1",
             "instagram_channel_id": True, "x_channel_id": True}]})
        with patch("app.marketing_api.MarketingConfig.load", return_value=_config()), \
                patch("app.marketing_api._run", return_value=payload):
            response = self.client.get("/company/marketing/buffer-accounts", auth=self.auth)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["accounts"][0]["name"], "default")
        self.assertNotIn("key", json.dumps(body).lower())


if __name__ == "__main__":
    unittest.main()
