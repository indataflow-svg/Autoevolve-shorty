import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from g3_runtime.accounts import list_accounts, load_account
from g3_runtime.buffer import BufferClient
from g3_runtime.errors import G3Error
from g3_runtime.handoff import SCHEMA, load_handoff
from g3_runtime.ledger import Ledger
from g3_runtime.r2 import verify_public_media
from g3_runtime.service import build_input, build_schedule_input, channel_id, idempotency_key, parse_due_at, submit_handoff, submit_schedule


class FakeClient:
    def __init__(self): self.created = []
    def create_draft(self, post_input):
        self.created.append(post_input)
        return {"id": f"draft-{len(self.created)}", "status": "draft", "text": post_input["text"]}


class FakeUploader:
    def __init__(self): self.uploads = []
    def upload(self, campaign_id, media):
        self.uploads.append((campaign_id, media.path.name))
        return f"https://media.example/{campaign_id}/{media.path.name}"


class FakeResponse:
    def __init__(self, body=b"\x00\x00\x00\x18ftypmp42", content_type="video/mp4", status=206,
                 url="https://media.example/video.mp4", headers=None):
        self.body = body
        self.status = status
        self.url = url
        self.headers = {"Content-Type": content_type, **(headers or {})}

    def __enter__(self): return self
    def __exit__(self, *_): return None
    def read(self, _size=-1): return self.body
    def getcode(self): return self.status
    def geturl(self): return self.url


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.media = self.root / "slide.png"
        self.media.write_bytes(b"png-placeholder")
        self.sha = hashlib.sha256(self.media.read_bytes()).hexdigest()

    def tearDown(self): self.tmp.cleanup()

    def write(self, value):
        path = self.root / "handoff.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def base(self):
        return {
            "schema": SCHEMA, "campaign_id": "camp_1", "source_package_sha256": "a" * 64,
            "publish_allowed": False,
            "drafts": [{"platform": "instagram", "channel_id": "ig1", "content": "Caption",
                        "media": [{"path": "slide.png", "sha256": self.sha}]}],
        }

    def test_ready_handoff_passes(self):
        self.assertEqual(load_handoff(self.write(self.base())).campaign_id, "camp_1")

    def test_publish_allowed_is_denied(self):
        value = self.base(); value["publish_allowed"] = True
        with self.assertRaises(G3Error): load_handoff(self.write(value))

    def test_schedule_field_is_denied(self):
        value = self.base(); value["scheduled_at"] = "tomorrow"
        with self.assertRaises(G3Error): load_handoff(self.write(value))

    def test_asset_escape_is_denied(self):
        value = self.base(); value["drafts"][0]["media"][0]["path"] = "../outside.png"
        with self.assertRaises(G3Error): load_handoff(self.write(value))

    def test_hash_mismatch_is_denied(self):
        value = self.base(); value["drafts"][0]["media"][0]["sha256"] = "bad"
        with self.assertRaises(G3Error): load_handoff(self.write(value))

    def test_instagram_requires_media(self):
        value = self.base(); value["drafts"][0]["media"] = []
        with self.assertRaises(G3Error): load_handoff(self.write(value))

    def test_obsolete_postiz_integration_id_is_denied(self):
        value = self.base(); value["drafts"][0]["integration_id"] = "old"
        with self.assertRaises(G3Error): load_handoff(self.write(value))

    def test_x_thread_payload_contains_root_and_reply(self):
        value = self.base()
        value["drafts"] = [{"platform": "x", "channel_id": "x1", "thread": [
            {"content": "one", "media": []}, {"content": "two", "media": []}]}]
        entry = load_handoff(self.write(value)).entries[0]
        payload = build_input(entry, "x1", [[], []])
        self.assertEqual(payload["text"], "one")
        self.assertEqual([part["text"] for part in payload["metadata"]["twitter"]["thread"]], ["one", "two"])
        self.assertIs(payload["saveToDraft"], True)

    def test_instagram_payload_is_ordered_and_draft_only(self):
        entry = load_handoff(self.write(self.base())).entries[0]
        payload = build_input(entry, "ig1", [["https://media.example/slide.png"]])
        self.assertEqual(payload["assets"][0]["image"]["url"], "https://media.example/slide.png")
        self.assertEqual(payload["metadata"]["instagram"]["type"], "post")
        self.assertNotIn("dueAt", payload)
        self.assertTrue(payload["saveToDraft"])

    def test_submit_confirms_and_records_draft(self):
        handoff = load_handoff(self.write(self.base()))
        client, uploader = FakeClient(), FakeUploader()
        ledger = Ledger(self.root / "ledger.db")
        report = submit_handoff(client, uploader, ledger, handoff)
        self.assertEqual(report["results"][0]["status"], "draft_confirmed")
        self.assertTrue(client.created[0]["saveToDraft"])
        self.assertEqual(uploader.uploads, [("camp_1", "slide.png")])

    def test_idempotency_skips_duplicate(self):
        handoff = load_handoff(self.write(self.base()))
        client, uploader = FakeClient(), FakeUploader()
        ledger = Ledger(self.root / "ledger.db")
        submit_handoff(client, uploader, ledger, handoff)
        report = submit_handoff(client, uploader, ledger, handoff)
        self.assertEqual(len(client.created), 1)
        self.assertEqual(report["results"][0]["status"], "duplicate_skipped")

    def test_key_is_stable(self):
        handoff = load_handoff(self.write(self.base())); entry = handoff.entries[0]
        self.assertEqual(idempotency_key(handoff, entry, "ig1"), idempotency_key(handoff, entry, "ig1"))

    def test_buffer_boundary_rejects_non_draft(self):
        client = BufferClient("test")
        with self.assertRaises(G3Error):
            client.create_draft({"saveToDraft": False, "mode": "shareNow"})

    @patch("g3_runtime.r2.urlopen", return_value=FakeResponse())
    def test_public_mp4_probe_passes(self, mocked):
        video = self.root / "video.mp4"
        video.write_bytes(b"\x00\x00\x00\x18ftypmp42")
        verify_public_media(
            "https://media.example/video.mp4",
            type("M", (), {"path": video})(),
            "video/mp4",
            attempts=1,
        )
        self.assertEqual(mocked.call_count, 1)

    @patch("g3_runtime.r2.urlopen", return_value=FakeResponse(content_type="text/html", body=b"login"))
    def test_public_mp4_probe_rejects_html(self, _mocked):
        video = self.root / "video.mp4"
        video.write_bytes(b"\x00\x00\x00\x18ftypmp42")
        with self.assertRaisesRegex(G3Error, "Content-Type text/html"):
            verify_public_media(
                "https://media.example/video.mp4",
                type("M", (), {"path": video})(),
                "video/mp4",
                attempts=1,
            )

    @patch("g3_runtime.r2.urlopen", return_value=FakeResponse(headers={"cf-mitigated": "challenge"}))
    def test_public_mp4_probe_rejects_cloudflare_challenge(self, _mocked):
        video = self.root / "video.mp4"
        video.write_bytes(b"\x00\x00\x00\x18ftypmp42")
        with self.assertRaisesRegex(G3Error, "Cloudflare challenge"):
            verify_public_media(
                "https://media.example/video.mp4",
                type("M", (), {"path": video})(),
                "video/mp4",
                attempts=1,
            )


class FakeScheduler:
    def __init__(self): self.created = []
    def create_scheduled(self, post_input):
        self.created.append(post_input)
        return {"id": f"post-{len(self.created)}", "status": "scheduled",
                "text": post_input["text"], "dueAt": post_input.get("dueAt")}


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.media = self.root / "slide.png"
        self.media.write_bytes(b"png-placeholder")
        self.sha = hashlib.sha256(self.media.read_bytes()).hexdigest()

    def tearDown(self): self.tmp.cleanup()

    def write(self, value):
        path = self.root / "handoff.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def base(self):
        return {
            "schema": SCHEMA, "campaign_id": "camp_1", "source_package_sha256": "a" * 64,
            "publish_allowed": False,
            "drafts": [{"platform": "instagram", "channel_id": "ig1", "content": "Caption",
                        "media": [{"path": "slide.png", "sha256": self.sha}]}],
        }

    def test_queue_input_has_no_draft_or_due_date(self):
        entry = load_handoff(self.write(self.base())).entries[0]
        payload = build_schedule_input(entry, "ig1", [["https://media.example/slide.png"]], mode="queue")
        self.assertIs(payload["saveToDraft"], False)
        self.assertEqual((payload["schedulingType"], payload["mode"]), ("automatic", "addToQueue"))
        self.assertNotIn("dueAt", payload)

    def test_timed_input_carries_normalized_due_date(self):
        entry = load_handoff(self.write(self.base())).entries[0]
        payload = build_schedule_input(entry, "ig1", [["https://media.example/slide.png"]],
                                       mode="timed", due_at="2999-01-02T10:00:00Z")
        self.assertEqual((payload["schedulingType"], payload["mode"]), ("custom", "customScheduled"))
        self.assertEqual(payload["dueAt"], "2999-01-02T10:00:00Z")

    def test_timed_requires_future_due_date(self):
        entry = load_handoff(self.write(self.base())).entries[0]
        with self.assertRaises(G3Error):
            build_schedule_input(entry, "ig1", [["https://media.example/slide.png"]], mode="timed")
        with self.assertRaises(G3Error):
            build_schedule_input(entry, "ig1", [["https://media.example/slide.png"]],
                                 mode="timed", due_at="2000-01-01T00:00:00Z")
        with self.assertRaises(G3Error):
            build_schedule_input(entry, "ig1", [["https://media.example/slide.png"]],
                                 mode="queue", due_at="2999-01-02T10:00:00Z")
        with self.assertRaises(G3Error):
            build_schedule_input(entry, "ig1", [["https://media.example/slide.png"]], mode="now")

    def test_parse_due_at_accepts_offsets_and_rejects_past(self):
        self.assertEqual(parse_due_at("2999-06-01T12:00:00+02:00"), "2999-06-01T10:00:00Z")
        self.assertIsNone(parse_due_at(None))
        self.assertIsNone(parse_due_at("  "))
        with self.assertRaises(G3Error):
            parse_due_at("not-a-date")
        with self.assertRaises(G3Error):
            parse_due_at("2000-01-01T00:00:00Z")

    def test_submit_schedule_records_and_dedupes(self):
        handoff = load_handoff(self.write(self.base()))
        client, uploader = FakeScheduler(), FakeUploader()
        ledger = Ledger(self.root / "ledger.db")
        report = submit_schedule(client, uploader, ledger, handoff, "queue", None)
        self.assertTrue(report["scheduled"])
        self.assertFalse(report["draft_only"])
        self.assertEqual(report["results"][0]["status"], "scheduled")
        rerun = submit_schedule(client, uploader, ledger, handoff, "queue", None)
        self.assertEqual(len(client.created), 1)
        self.assertEqual(rerun["results"][0]["status"], "duplicate_skipped")
        other_slot = submit_schedule(client, uploader, ledger, handoff, "timed", "2999-01-02T10:00:00Z")
        self.assertEqual(len(client.created), 2)
        self.assertEqual(other_slot["results"][0]["due_at"], "2999-01-02T10:00:00Z")

    def test_schedule_boundary_rejects_draft_inputs(self):
        client = BufferClient("test")
        with self.assertRaises(G3Error):
            client.create_scheduled({"saveToDraft": True, "mode": "addToQueue"})
        with self.assertRaises(G3Error):
            client.create_scheduled({"saveToDraft": False, "mode": "shareNow"})
        with self.assertRaises(G3Error):
            client.create_scheduled({"saveToDraft": False, "mode": "customScheduled"})
        with self.assertRaises(G3Error):
            client.create_scheduled({"saveToDraft": False, "mode": "addToQueue",
                                     "dueAt": "2999-01-02T10:00:00Z"})

    def test_schedule_accepts_buffer_confirmation(self):
        client = BufferClient("test")
        with patch.object(BufferClient, "_request", return_value={
                "createPost": {"__typename": "PostActionSuccess",
                               "post": {"id": "post-1", "status": "pending"}}}):
            post = client.create_scheduled({"saveToDraft": False, "mode": "addToQueue"})
        self.assertEqual(post["id"], "post-1")


class AccountTests(unittest.TestCase):
    def test_default_account_reads_unprefixed_vars(self):
        env = {"BUFFER_API_KEY": "key-1", "BUFFER_ORGANIZATION_ID": "org-1",
               "BUFFER_INSTAGRAM_CHANNEL_ID": "ig-1", "BUFFER_X_CHANNEL_ID": "x-1"}
        with patch.dict("os.environ", env, clear=True):
            account = load_account(None)
        self.assertEqual(account.name, "default")
        self.assertEqual(account.api_key, "key-1")
        self.assertEqual(account.channel_for("x"), "x-1")
        self.assertEqual(account.channel_for("instagram"), "ig-1")

    def test_named_account_reads_prefixed_vars(self):
        env = {"BUFFER_API_KEY": "key-1",
               "BUFFER_ACME_API_KEY": "key-2", "BUFFER_ACME_X_CHANNEL_ID": "x-2"}
        with patch.dict("os.environ", env, clear=True):
            account = load_account("acme")
        self.assertEqual(account.name, "acme")
        self.assertEqual(account.api_key, "key-2")
        self.assertEqual(account.channel_for("x"), "x-2")
        with self.assertRaises(G3Error):
            account.channel_for("instagram")

    def test_missing_key_and_bad_name_raise(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(G3Error):
                load_account(None)
            with self.assertRaises(G3Error):
                load_account("NOPE bad name!")

    def test_list_accounts_masks_keys(self):
        env = {"BUFFER_API_KEY": "key-1", "BUFFER_ACME_API_KEY": "key-2",
               "BUFFER_ACME_X_CHANNEL_ID": "x-2"}
        with patch.dict("os.environ", env, clear=True):
            accounts = list_accounts()
        by_name = {item["name"]: item for item in accounts}
        self.assertEqual(set(by_name), {"default", "acme"})
        self.assertTrue(by_name["acme"]["x_channel_id"])
        self.assertNotIn("key-2", json.dumps(accounts))

    def test_channel_id_prefers_entry_then_account(self):
        from g3_runtime.handoff import Entry
        env = {"BUFFER_API_KEY": "key-1", "BUFFER_X_CHANNEL_ID": "x-env"}
        with patch.dict("os.environ", env, clear=True):
            account = load_account("default")
            explicit = Entry("x", "x-explicit", [])
            self.assertEqual(channel_id(explicit, account), "x-explicit")
            implicit = Entry("x", None, [])
            self.assertEqual(channel_id(implicit, account), "x-env")
            with self.assertRaises(G3Error):
                channel_id(Entry("instagram", None, []), account)

    def test_submit_carries_account_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media = root / "slide.png"
            media.write_bytes(b"png-placeholder")
            sha = hashlib.sha256(media.read_bytes()).hexdigest()
            path = root / "handoff.json"
            path.write_text(json.dumps({
                "schema": SCHEMA, "campaign_id": "camp_9", "source_package_sha256": "c" * 64,
                "publish_allowed": False,
                "drafts": [{"platform": "x", "thread": [{"content": "Caption", "media": []}]}],
            }), encoding="utf-8")
            handoff = load_handoff(path)
            env = {"BUFFER_API_KEY": "key-1", "BUFFER_BETA_API_KEY": "key-2",
                   "BUFFER_BETA_X_CHANNEL_ID": "x-beta"}
            with patch.dict("os.environ", env, clear=True):
                account = load_account("beta")
                client, uploader = FakeClient(), FakeUploader()
                report = submit_handoff(client, uploader, Ledger(root / "ledger.db"),
                                        handoff, False, account)
            self.assertEqual(report["account"], "beta")
            self.assertEqual(report["results"][0]["status"], "draft_confirmed")


if __name__ == "__main__": unittest.main()
