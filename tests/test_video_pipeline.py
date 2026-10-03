"""Integration test: corridor script -> VideoSpec -> ShotPlan -> RenderJobs -> queue.

Uses the real pipeline services and the real FastAPI app against a temporary
database. The model router is unconfigured here, so the deterministic planning
path is exercised (AI enhancement is assist-only and always falls back).
"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api import app
from core import state, video_store
from services import video_pipeline

CORRIDOR = Path(__file__).resolve().parent.parent / "scripts" / "indataflow" / "corridor.md"


class VideoPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        database = Path(self.temporary.name) / "company.db"
        self.original = (state.DB_PATH, video_store.DB_PATH)
        state.DB_PATH = database
        video_store.DB_PATH = database
        state.init_db()
        video_store.init_video_db()
        self.env = patch.dict(os.environ, {
            "DASHBOARD_USER": "founder",
            "DASHBOARD_PASSWORD": "dashboard-secret",
            "SALES_ACTION_TOKEN": "action-secret",
            "OMNIROUTE_API_KEY": "",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.client = TestClient(app)
        self.auth = ("founder", "dashboard-secret")
        self.token_headers = {"X-Founder-Action-Token": "action-secret"}

    def tearDown(self):
        state.DB_PATH, video_store.DB_PATH = self.original
        self.temporary.cleanup()

    # -- script -> spec -> plan -> jobs -----------------------------------

    def test_corridor_script_produces_spec_plan_and_jobs(self):
        result = video_pipeline.plan_video(
            CORRIDOR, project_id="indataflow-corridor", aspect_ratio="9:16", fps=24
        )
        spec, plan, jobs = result["spec"], result["plan"], result["jobs"]

        # 1 VideoSpec / 1 ShotPlan / ~6 Shots
        self.assertTrue(spec["id"].startswith("vspec_"))
        self.assertEqual(spec["title"], "The New Corridor Needs a Record")
        self.assertEqual(len(spec["transcript"]), 6)
        # Transcript wording is preserved verbatim from the source script.
        self.assertIn("THE NEW CORRIDOR", spec["transcript"][0]["text"])
        self.assertEqual(spec["format"]["durationSeconds"], 50)
        self.assertEqual(spec["format"]["width"], 1080)
        self.assertEqual(spec["format"]["height"], 1920)
        self.assertEqual(result["ai"]["source"], "deterministic")

        self.assertTrue(plan["id"].startswith("splan_"))
        self.assertEqual(plan["video_spec_id"], spec["id"])
        self.assertEqual(len(plan["shots"]), 6)

        # Script timing preserved shot by shot.
        for shot, beat in zip(plan["shots"], spec["transcript"]):
            self.assertEqual(shot["transcriptBeatIds"], [beat["id"]])
            self.assertEqual(shot["startSeconds"], beat["startSeconds"])
            self.assertEqual(shot["endSeconds"], beat["endSeconds"])

        # Visual types assigned; every shot renders; continuity chained.
        visual_types = {shot["visualType"] for shot in plan["shots"]}
        self.assertTrue(visual_types <= set(video_pipeline.VISUAL_TYPES))
        self.assertTrue(all(shot["renderRequired"] for shot in plan["shots"]))
        self.assertIsNone(plan["shots"][0]["continuity"]["previousShot"])
        self.assertEqual(
            plan["shots"][0]["continuity"]["nextShot"], plan["shots"][1]["id"]
        )

        # Hunyuan jobs for cinematic shots, asset jobs for stock/product/source.
        renderers = {job["renderer"] for job in jobs}
        self.assertIn("hunyuan", renderers)
        self.assertIn("asset", renderers)
        self.assertEqual(len(jobs), 6)
        hunyuan_jobs = [job for job in jobs if job["renderer"] == "hunyuan"]
        self.assertTrue(hunyuan_jobs)
        for job in hunyuan_jobs:
            self.assertTrue(job["prompt"] and len(job["prompt"]) > 20)
            self.assertIn("watermark", (job["negativePrompt"] or ""))
            self.assertEqual(job["model"], "HunyuanVideo-1.5")
            self.assertEqual(job["resolution"], "480p")
            self.assertEqual(job["dtype"], "bf16")

        # Render profiles generated: frames correspond to duration x FPS.
        for job, shot in zip(jobs, plan["shots"]):
            self.assertEqual(job["frames"], round(shot["durationSeconds"] * 24))
            self.assertEqual(job["fps"], 24)
            self.assertIsNotNone(job["seed"])
            self.assertEqual(job["shotPlanId"], plan["id"])
            self.assertEqual(job["videoSpecId"], spec["id"])

        # RenderJobs serialized correctly: unique outputs under the project.
        outputs = [job["outputPath"] for job in jobs]
        self.assertEqual(len(set(outputs)), 6)
        self.assertTrue(all(path.startswith("videos/indataflow-corridor/shots/") for path in outputs))

    def test_broken_timestamps_are_rejected(self):
        parsed = video_pipeline.parse_script("## 0:10–0:05\nBackwards beat.\n", source_name="bad.md")
        spec = video_pipeline.build_spec(parsed, project_id="bad", context={})
        with self.assertRaises(ValueError):
            video_pipeline.validate_spec(spec)

    def test_prohibited_claims_are_rejected(self):
        parsed = video_pipeline.parse_script(CORRIDOR.read_text(encoding="utf-8"))
        context = video_pipeline.load_indataflow_context()
        spec = video_pipeline.build_spec(parsed, project_id="x", context=context)
        plan, _ = video_pipeline.plan_shots({**spec, "id": "v"}, context, use_ai=False)
        plan["shots"][0]["purpose"] = "This guarantees clearance in half the time, 10x faster."
        with self.assertRaises(ValueError):
            video_pipeline.validate_claims(spec, plan, context)

    # -- queue operations ---------------------------------------------------

    def _queued_corridor(self):
        result = video_pipeline.plan_video(CORRIDOR, project_id="indataflow-corridor")
        queued = video_pipeline.queue_shot_plan(result["plan"]["id"])
        self.assertFalse(queued["already_queued"])
        return result, queued

    def test_queue_accepts_jobs_and_worker_leases_hunyuan_job(self):
        _result, queued = self._queued_corridor()
        self.assertEqual(queued["counts"]["total"], 6)

        job = video_store.lease_next_job("mi300x-01", renderer="hunyuan")
        self.assertIsNotNone(job)
        self.assertEqual(job["renderer"], "hunyuan")
        self.assertEqual(job["status"], "leased")
        self.assertEqual(job["worker_id"], "mi300x-01")
        self.assertEqual(job["attempts"], 1)

        heartbeat = video_store.heartbeat_job(job["id"], "mi300x-01")
        self.assertEqual(heartbeat["status"], "running")

        done = video_store.complete_job(
            job["id"], "mi300x-01",
            result={"outputPath": job["output_path"], "frames": job["frames"]},
        )
        self.assertEqual(done["status"], "completed")
        self.assertEqual(done["result"]["frames"], done["frames"])

    def test_failed_retryable_job_returns_to_pending(self):
        self._queued_corridor()
        job = video_store.lease_next_job("mi300x-01")
        failed = video_store.fail_job(job["id"], "mi300x-01", code="OOM", message="out of memory",
                                      retryable=True)
        self.assertEqual(failed["status"], "pending")
        self.assertIsNone(failed["worker_id"])

        job = video_store.lease_next_job("mi300x-01")
        failed = video_store.fail_job(job["id"], "mi300x-01", code="BAD", message="bad",
                                      retryable=False)
        self.assertEqual(failed["status"], "failed")

        retried = video_store.retry_job(job["id"])
        self.assertEqual(retried["status"], "pending")
        self.assertEqual(retried["attempts"], 0)

    def test_expired_lease_is_reclaimed(self):
        self._queued_corridor()
        leased = []
        while True:
            job = video_store.lease_next_job("mi300x-01")
            if not job:
                break
            leased.append(job)
        self.assertEqual(len(leased), 6)
        with video_store.connect() as connection:
            connection.execute(
                "UPDATE video_render_jobs SET leased_until = '2000-01-01T00:00:00+00:00' WHERE id = ?",
                (leased[0]["id"],),
            )
        reclaimed = video_store.lease_next_job("mi300x-02")
        self.assertEqual(reclaimed["id"], leased[0]["id"])
        self.assertEqual(reclaimed["worker_id"], "mi300x-02")

    def test_cancel_and_double_queue(self):
        _result, queued = self._queued_corridor()
        cancellable = next(job for job in queued["queued"] if job["status"] == "pending")
        cancelled = video_store.cancel_job(cancellable["id"])
        self.assertEqual(cancelled["status"], "cancelled")

        again = video_pipeline.queue_shot_plan(_result["plan"]["id"])
        self.assertTrue(again["already_queued"])
        self.assertEqual(again["counts"]["total"], 6)

    # -- HTTP worker protocol -------------------------------------------------

    def test_worker_protocol_over_http(self):
        result = video_pipeline.plan_video(CORRIDOR, project_id="indataflow-corridor")
        video_pipeline.queue_shot_plan(result["plan"]["id"])

        response = self.client.get(
            "/company/video/render-jobs/next",
            params={"worker_id": "mi300x-01", "renderer": "hunyuan"},
            auth=self.auth,
        )
        self.assertEqual(response.status_code, 200, response.text)
        job = response.json()["job"]
        self.assertIsNotNone(job)
        self.assertEqual(job["renderer"], "hunyuan")
        self.assertIn("prompt", job)
        self.assertIn("frames", job)

        response = self.client.post(
            f"/company/video/render-jobs/{job['id']}/complete",
            params={"worker_id": "mi300x-01"},
            json={"result": {"outputPath": job["output_path"]}},
            auth=self.auth,
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["job"]["status"], "completed")

        response = self.client.get("/company/video/queue/stats", auth=self.auth)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["by_status"]["completed"], 1)

    def test_video_auth_and_action_gate(self):
        response = self.client.get("/company/video/specs")
        self.assertEqual(response.status_code, 401)

        result = video_pipeline.plan_video(CORRIDOR, project_id="indataflow-corridor")
        response = self.client.post(
            f"/company/video/plans/{result['plan']['id']}/queue", auth=self.auth
        )
        self.assertEqual(response.status_code, 403)
        response = self.client.post(
            f"/company/video/plans/{result['plan']['id']}/queue",
            auth=self.auth,
            headers=self.token_headers,
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["counts"]["total"], 6)

    def test_hunyuan_profile_endpoint(self):
        response = self.client.get("/company/video/hunyuan/profile", auth=self.auth)
        self.assertEqual(response.status_code, 200, response.text)
        profile = response.json()
        self.assertEqual(profile["resolution"], "480p")
        self.assertEqual(profile["fps"], 24)
        self.assertEqual(profile["steps"], 20)
        self.assertEqual(profile["dtype"], "bf16")
        self.assertEqual(profile["seed"], 42)


if __name__ == "__main__":
    unittest.main()
