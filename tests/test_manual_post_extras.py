import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from app.api import app
import core.marketing_store as marketing_store
import core.state as state


def _png(color=(10, 120, 200)):
    frame = Image.new("RGB", (64, 64), color)
    buffer = io.BytesIO()
    frame.save(buffer, "PNG")
    return buffer.getvalue()


class FakeVisionResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def _vision_ok(*args, **kwargs):
    return FakeVisionResponse({"choices": [{"message": {"content": json.dumps({
        "title": "Dispatch board walkthrough",
        "caption": "Line one.\nLine two.\nGet the ops audit: https://example.com",
    })}}]})


class ManualPostExtrasTests(unittest.TestCase):
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
        self.other = state.create_org("Second Brand", "second-brand", env_prefix="BUFFER_")
        state.set_active_org(self.project["id"])
        self.client = TestClient(app)
        self.auth = ("founder", "dashboard-secret")
        self.env = patch.dict(os.environ, {
            "DASHBOARD_USER": "founder",
            "DASHBOARD_PASSWORD": "dashboard-secret",
            "OMNIROUTE_API_KEY": "vision-test-key",
        }, clear=False)
        self.env.start()
        from app.marketing_api import PROJECTS_ROOT
        self.asset_root = PROJECTS_ROOT / ".test-ai-tmp"
        self.asset_root.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.asset_root, ignore_errors=True)
        self.env.stop()
        state.DB_PATH = self.old_state_path
        marketing_store.DB_PATH = self.old_marketing_path
        self.temporary.cleanup()

    def _post(self, **overrides):
        self._post_seq = getattr(self, "_post_seq", 0) + 1
        values = {
            "org_id": self.project["id"], "platform": "x", "post_id": f"x_post_ai_{self._post_seq}",
            "destination_url": "https://example.com", "tracked_url": "https://example.com/?x=1",
            "asset_dir": str(self.asset_root), "assets": [{"filename": "slide1.png"}],
            "metadata": {"post_type": "carousel", "workflow_status": "ready"},
        }
        values.update(overrides)
        (self.asset_root / "slide1.png").write_bytes(_png())
        return marketing_store.create_manual_post(**values)

    def test_linkedin_post_builds_a_handoff_entry(self):
        from app.marketing_api import _manual_post_handoff

        post = self._post(platform="linkedin", post_id="li_post_1")
        handoff_path, asset_root = _manual_post_handoff(post)
        payload = json.loads(handoff_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["drafts"][0]["platform"], "linkedin")
        self.assertEqual(len(payload["drafts"][0]["media"]), 1)
        self.assertEqual(asset_root, self.asset_root.resolve())

    def test_orgs_list_and_reassign(self):
        response = self.client.get("/company/marketing/orgs", auth=self.auth)
        self.assertEqual(response.status_code, 200, response.text)
        slugs = {item["slug"] for item in response.json()["orgs"]}
        self.assertTrue({"company-core", "second-brand"} <= slugs)

        post = self._post()
        moved = self.client.post(f"/company/marketing/manual-posts/{post['id']}/org",
                                 auth=self.auth, json={"org_id": self.other["id"]})
        self.assertEqual(moved.status_code, 200, moved.text)
        self.assertEqual(moved.json()["post"]["org_id"], self.other["id"])

        missing = self.client.post(f"/company/marketing/manual-posts/{post['id']}/org",
                                   auth=self.auth, json={"org_id": 999999})
        self.assertEqual(missing.status_code, 404)

    def test_ai_caption_reads_slides_and_stores_copy(self):
        post = self._post()
        with patch("urllib.request.urlopen", side_effect=_vision_ok):
            response = self.client.post(f"/company/marketing/manual-posts/{post['id']}/ai-caption",
                                        auth=self.auth)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["result"]["title"], "Dispatch board walkthrough")
        stored = marketing_store.get_manual_post(post["id"])
        self.assertEqual(stored["title"], "Dispatch board walkthrough")
        self.assertIn("Line one.", stored["metadata"]["generated_caption"])
        self.assertEqual(stored["metadata"]["ai_caption_slides"], 1)

    def test_ai_caption_rejects_video_and_missing_key(self):
        post = self._post(metadata={"post_type": "video", "workflow_status": "ready"})
        with patch("urllib.request.urlopen", side_effect=_vision_ok):
            denied = self.client.post(f"/company/marketing/manual-posts/{post['id']}/ai-caption",
                                      auth=self.auth)
        self.assertEqual(denied.status_code, 422)

        carousel = self._post()
        with patch.dict(os.environ, {"OMNIROUTE_API_KEY": ""}, clear=False):
            keyless = self.client.post(f"/company/marketing/manual-posts/{carousel['id']}/ai-caption",
                                       auth=self.auth)
        self.assertEqual(keyless.status_code, 409)


    def test_session_honors_explicit_org(self):
        response = self.client.post("/company/marketing/manual-posts/session", auth=self.auth, json={
            "platform": "x", "post_type": "carousel", "org_id": self.other["id"]})
        self.assertEqual(response.status_code, 200, response.text)
        post = response.json()["post"]
        self.assertEqual(post["org_id"], self.other["id"])
        stored = marketing_store.get_manual_post(post["id"])
        self.assertIn("second-brand", stored["asset_dir"])

    def test_session_rejects_unknown_org(self):
        response = self.client.post("/company/marketing/manual-posts/session", auth=self.auth, json={
            "platform": "x", "post_type": "carousel", "org_id": 999999})
        self.assertEqual(response.status_code, 404)

    def test_session_defaults_to_active_org(self):
        response = self.client.post("/company/marketing/manual-posts/session", auth=self.auth, json={
            "platform": "x", "post_type": "carousel"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["post"]["org_id"], self.project["id"])

    def test_preview_is_read_only_and_matches_the_saved_caption(self):
        before = len(marketing_store.list_manual_posts(limit=200))
        payload = {
            "platform": "instagram",
            "post_type": "carousel",
            "link_label": "customs workflow audit",
            "filenames": ["trade-data-slide-1.png", "customs-delay-slide-2.png"],
        }
        with patch.dict(os.environ, {"MARKETING_FORMS_BASE_URL": "https://forms.test/apply"}, clear=False):
            preview = self.client.post("/company/marketing/manual-posts/preview", auth=self.auth, json=payload)
            self.assertEqual(preview.status_code, 200, preview.text)
            self.assertEqual(len(marketing_store.list_manual_posts(limit=200)), before, "preview must not persist a post")
            body = preview.json()
            self.assertEqual(body["default_destination_url"], "https://forms.test/apply")
            self.assertEqual(body["link_label"], "customs workflow audit")
            self.assertIn("Link in bio · customs workflow audit", body["caption"])
            self.assertIn("utm_source=instagram", body["tracked_url"])

            created = self.client.post(
                "/company/marketing/manual-posts",
                auth=self.auth,
                data={"platform": "instagram", "post_type": "carousel", "link_label": "customs workflow audit"},
                files=[("assets", ("trade-data-slide-1.png", _png(), "image/png")),
                       ("assets", ("customs-delay-slide-2.png", _png((200, 40, 40)), "image/png"))],
            )
        self.assertEqual(created.status_code, 200, created.text)
        saved = created.json()["post"]
        try:
            self.assertEqual(saved["caption"], body["caption"])
            self.assertEqual(saved["title"], body["title"])
            self.assertTrue(saved["tracked_url"].startswith("https://forms.test/apply?"))
        finally:
            shutil.rmtree(Path(saved["asset_dir"]), ignore_errors=True)

    def test_preview_defaults_and_platform_rules(self):
        with patch.dict(os.environ, {"MARKETING_FORMS_BASE_URL": ""}, clear=False):
            blank = self.client.post("/company/marketing/manual-posts/preview", auth=self.auth, json={
                "platform": "x", "post_type": "video", "filenames": []})
        self.assertEqual(blank.status_code, 200, blank.text)
        body = blank.json()
        self.assertEqual(body["link_label"], "ops audit")
        self.assertEqual(body["title"], "X video")
        self.assertIn("Get the ops audit:", body["caption"])
        self.assertIn(body["tracked_url"], body["caption"])
        self.assertEqual(body["post_type"], "video")

        unsupported = self.client.post("/company/marketing/manual-posts/preview", auth=self.auth, json={
            "platform": "myspace", "post_type": "carousel"})
        self.assertEqual(unsupported.status_code, 422)

        bad_type = self.client.post("/company/marketing/manual-posts/preview", auth=self.auth, json={
            "platform": "x", "post_type": "reel"})
        self.assertEqual(bad_type.status_code, 422)

        bad_url = self.client.post("/company/marketing/manual-posts/preview", auth=self.auth, json={
            "platform": "x", "post_type": "carousel", "destination_url": "ftp://example.com"})
        self.assertEqual(bad_url.status_code, 422)

if __name__ == "__main__":
    unittest.main()
