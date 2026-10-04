"""Tests for the phase-1 MI300X submit path (services/renderers.py).

A stdlib HTTP worker double stands in for the real Tailscale worker, in its
modes: valid MP4 bytes, JSON output_url, HTTP 500, 422, timeout (sleep),
malformed body, and corrupt video bytes. No GPU or network is touched; the
real ffprobe binary validates the QA success path (skipped if absent).
"""
import json
import os
import shutil
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from core import state, video_store
from services import renderers
from services import video_pipeline

CORRIDOR = Path(__file__).resolve().parent.parent / "scripts" / "indataflow" / "corridor.md"
HAS_FFPROBE = shutil.which("ffprobe") is not None
HAS_FFMPEG = shutil.which("ffmpeg") is not None


def make_test_mp4(frames: int = 144, fps: int = 24) -> bytes:
    duration = frames / fps
    with tempfile.TemporaryDirectory(prefix="fixture-mp4-") as tmp:
        out = Path(tmp) / "fixture.mp4"
        result = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", f"testsrc=duration={duration}:size=64x64:rate={fps}",
                "-pix_fmt", "yuv420p", "-c:v", "libx264", "-y", str(out),
            ],
            capture_output=True,
            timeout=120,
        )
        if result.returncode or not out.is_file():
            raise RuntimeError("could not generate fixture MP4")
        return out.read_bytes()


class WorkerDouble(BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep test output clean
        pass

    def _json(self, payload, status=200):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._json({"status": "healthy", "worker_id": "mi300x-01", "renderer": "hunyuan"})
        elif self.path == "/capacity":
            self._json({"status": "available", "worker_id": "mi300x-01", "renderer": "hunyuan"})
        elif self.path == "/files/out.mp4":
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(self.server.mp4_bytes)))
            self.end_headers()
            self.wfile.write(self.server.mp4_bytes)
        else:
            self._json({"detail": "not found"}, status=404)

    def do_POST(self):
        if self.path != "/render":
            self._json({"detail": "not found"}, status=404)
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(raw.decode() or "{}")
        except ValueError:
            payload = {}
        self.server.last_payload = payload
        mode = self.server.mode
        if mode == "ok-bytes":
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(self.server.mp4_bytes)))
            self.end_headers()
            self.wfile.write(self.server.mp4_bytes)
        elif mode == "ok-json-url":
            port = self.server.server_address[1]
            self._json({"output_url": f"http://127.0.0.1:{port}/files/out.mp4"})
        elif mode == "http500":
            self._json({"detail": "CUDA out of memory"}, status=500)
        elif mode == "validation":
            self._json({"detail": "Field required"}, status=422)
        elif mode == "sleep":
            import time as _time

            _time.sleep(5)
            self._json({"output_url": "http://127.0.0.1:1/none"})
        elif mode == "malformed":
            body = b"definitely not json"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif mode == "completed-local-path":
            self._json({
                "status": "completed",
                "worker_id": "mi300x-01",
                "job_id": "job_test",
                "output_path": "/root/video-lab/outputs/shot_001.mp4",
                "size_bytes": 782773,
            })
        elif mode == "garbage-video":
            body = os.urandom(2048)
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self._json({"detail": f"unknown mode {mode}"}, status=500)


@unittest.skipUnless(HAS_FFMPEG and HAS_FFPROBE, "ffmpeg/ffprobe required for worker-double tests")
class HunyuanRendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mp4_bytes = make_test_mp4()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        database = Path(self.temporary.name) / "company.db"
        self.original = (state.DB_PATH, video_store.DB_PATH)
        state.DB_PATH = database
        video_store.DB_PATH = database
        state.init_db()
        video_store.init_video_db()
        self.renders = Path(self.temporary.name) / "renders"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), WorkerDouble)
        self.server.mode = "ok-bytes"
        self.server.mp4_bytes = self.mp4_bytes
        self.server.last_payload = None
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        port = self.server.server_address[1]
        self.env = patch.dict(os.environ, {
            "OMNIROUTE_API_KEY": "",
            "RENDER_WORKER_URL": f"http://127.0.0.1:{port}",
            "RENDER_OUTPUT_DIR": str(self.renders),
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        planned = video_pipeline.plan_video(CORRIDOR, project_id="indataflow-corridor")
        video_pipeline.queue_shot_plan(planned["plan"]["id"])
        self.hunyuan_job = next(
            job for job in video_store.list_jobs() if job["renderer"] == "hunyuan"
        )

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        state.DB_PATH, video_store.DB_PATH = self.original
        self.temporary.cleanup()

    # -- probes -----------------------------------------------------------

    def test_health_and_capacity(self):
        with renderers.HunyuanRenderer() as renderer:
            health = renderer.check_health()
            capacity = renderer.check_capacity()
        self.assertEqual(health["status"], "healthy")
        self.assertEqual(capacity["status"], "available")

    def test_unreachable_worker_is_failure_tolerant(self):
        with renderers.HunyuanRenderer(base_url="http://127.0.0.1:1") as renderer:
            with self.assertRaises(renderers.RenderWorkerError) as raised:
                renderer.check_health()
        self.assertEqual(raised.exception.kind, "unreachable")
        self.assertTrue(raised.exception.retryable)
        status = renderers.worker_status()
        self.assertTrue(status["configured"])

    def test_worker_status_unconfigured(self):
        with patch.dict(os.environ, {"RENDER_WORKER_URL": ""}):
            status = renderers.worker_status()
        self.assertFalse(status["configured"])

    def test_submit_unconfigured_leaves_job_untouched(self):
        with patch.dict(os.environ, {"RENDER_WORKER_URL": ""}):
            with self.assertRaises(renderers.RenderWorkerError) as raised:
                renderers.submit_hunyuan_job(self.hunyuan_job["id"])
        self.assertEqual(raised.exception.kind, "not_configured")
        stored = video_store.get_job(self.hunyuan_job["id"])
        self.assertEqual(stored["status"], "pending")
        self.assertEqual(stored["attempts"], 0)
        self.assertIsNone(stored["error"])

    # -- submit success ----------------------------------------------------

    def test_submit_success_completes_job_with_qa_metadata(self):
        completed = renderers.submit_hunyuan_job(self.hunyuan_job["id"])
        self.assertEqual(completed["status"], "completed")
        result = completed["result"]
        saved = Path(result["outputPath"])
        self.assertTrue(saved.is_file())
        self.assertEqual(result["frames"], 144)
        self.assertEqual(result["fileSizeBytes"], len(self.mp4_bytes))
        self.assertEqual(len(result["metadata"]["sha256"]), 64)
        self.assertEqual(result["metadata"]["codec"], "h264")
        # The worker payload carries the full job contract, not just prompt.
        payload = self.server.last_payload
        self.assertTrue(payload["prompt"])
        self.assertEqual(payload["frames"], 144)
        self.assertEqual(payload["fps"], 24)
        self.assertEqual(payload["seed"], self.hunyuan_job["seed"])
        self.assertEqual(payload["dtype"], "bf16")
        self.assertEqual(payload["aspect_ratio"], "9:16")
        self.assertTrue(payload["output_name"].endswith(".mp4"))

    def test_submit_success_via_output_url(self):
        self.server.mode = "ok-json-url"
        completed = renderers.submit_hunyuan_job(self.hunyuan_job["id"])
        self.assertEqual(completed["status"], "completed")
        self.assertTrue(Path(completed["result"]["outputPath"]).is_file())

    # -- submit failures: recorded, never silently completed ---------------

    def test_submit_http500_returns_job_to_pending(self):
        self.server.mode = "http500"
        with self.assertRaises(renderers.RenderWorkerError) as raised:
            renderers.submit_hunyuan_job(self.hunyuan_job["id"])
        self.assertTrue(raised.exception.retryable)
        stored = video_store.get_job(self.hunyuan_job["id"])
        self.assertEqual(stored["status"], "pending")
        self.assertEqual(stored["error"]["code"], "http_500")
        self.assertEqual(stored["attempts"], 1)

    def test_submit_validation_error_is_not_retryable(self):
        self.server.mode = "validation"
        with self.assertRaises(renderers.RenderWorkerError) as raised:
            renderers.submit_hunyuan_job(self.hunyuan_job["id"])
        self.assertFalse(raised.exception.retryable)
        stored = video_store.get_job(self.hunyuan_job["id"])
        self.assertEqual(stored["status"], "failed")
        self.assertEqual(stored["error"]["code"], "validation")

    def test_submit_timeout_is_recorded(self):
        self.server.mode = "sleep"
        with self.assertRaises(renderers.RenderWorkerError) as raised:
            renderers.submit_hunyuan_job(self.hunyuan_job["id"], timeout_seconds=2)
        self.assertEqual(raised.exception.kind, "timeout")
        stored = video_store.get_job(self.hunyuan_job["id"])
        self.assertEqual(stored["status"], "pending")

    def test_malformed_response_is_recorded(self):
        self.server.mode = "malformed"
        with self.assertRaises(renderers.RenderWorkerError) as raised:
            renderers.submit_hunyuan_job(self.hunyuan_job["id"])
        self.assertEqual(raised.exception.kind, "malformed")
        stored = video_store.get_job(self.hunyuan_job["id"])
        self.assertEqual(stored["status"], "failed")

    def test_completed_without_download_is_terminal_with_recovery_info(self):
        # The worker rendered but returned only its local path: resubmitting
        # would burn GPU again, so the job fails terminally with everything
        # needed for manual recovery.
        self.server.mode = "completed-local-path"
        with self.assertRaises(renderers.RenderWorkerError) as raised:
            renderers.submit_hunyuan_job(self.hunyuan_job["id"])
        self.assertEqual(raised.exception.kind, "output_unavailable")
        self.assertFalse(raised.exception.retryable)
        stored = video_store.get_job(self.hunyuan_job["id"])
        self.assertEqual(stored["status"], "failed")
        self.assertEqual(stored["error"]["code"], "output_unavailable")
        self.assertIn("/root/video-lab/outputs/shot_001.mp4", stored["error"]["message"])
        self.assertIn("782773", stored["error"]["message"])

    def test_corrupt_video_fails_qa(self):
        self.server.mode = "garbage-video"
        with self.assertRaises(renderers.RenderWorkerError) as raised:
            renderers.submit_hunyuan_job(self.hunyuan_job["id"])
        self.assertEqual(raised.exception.kind, "qa_failed")
        stored = video_store.get_job(self.hunyuan_job["id"])
        self.assertEqual(stored["status"], "pending")
        self.assertEqual(stored["error"]["code"], "qa_failed")

    def test_exhausted_attempts_cannot_be_claimed(self):
        with video_store.connect() as connection:
            connection.execute(
                "UPDATE video_render_jobs SET attempts = max_attempts WHERE id = ?",
                (self.hunyuan_job["id"],),
            )
        with self.assertRaises(ValueError):
            renderers.submit_hunyuan_job(self.hunyuan_job["id"])

    def test_non_hunyuan_job_has_no_submitter(self):
        asset_job = next(job for job in video_store.list_jobs() if job["renderer"] == "asset")
        with self.assertRaises(renderers.RenderWorkerError) as raised:
            renderers.submit_hunyuan_job(asset_job["id"])
        self.assertEqual(raised.exception.kind, "no_submitter")
        # Rejected before claiming: the job is untouched.
        self.assertEqual(video_store.get_job(asset_job["id"])["status"], "pending")

    # -- unit checks --------------------------------------------------------

    def test_aspect_ratio_helper(self):
        self.assertEqual(renderers.aspect_ratio_for(1080, 1920), "9:16")
        self.assertEqual(renderers.aspect_ratio_for(1920, 1080), "16:9")
        self.assertEqual(renderers.aspect_ratio_for(848, 480), "53:30")
        self.assertEqual(renderers.aspect_ratio_for(None, None), "9:16")


if __name__ == "__main__":
    unittest.main()
