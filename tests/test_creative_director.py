"""Tests for the model-agnostic creative director (template-4 phases 3-11, 14-17, 20).

AI roles are exercised through fakes: no model key exists in tests, so every
AI assist must fall back deterministically or raise a clear configuration
error. The ffmpeg binary backs technical-review fixtures (skipped if absent).
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import state, video_store
from services import cinematography, motion_recipes, quality_gates, review, video_pipeline
from services.creative_director import (
    ROLE_ROUTES,
    CreativeDirector,
    DirectorUnavailable,
    director_available,
    require_director,
)
from services.visual_bible import default_bible, inherit_for_shot, validate_bible

CORRIDOR = Path(__file__).resolve().parent.parent / "scripts" / "indataflow" / "corridor.md"
HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def make_clip(frames=24, fps=24):
    directory = tempfile.mkdtemp(prefix="review-clip-")
    out = Path(directory) / "clip.mp4"
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", f"testsrc=duration={frames / fps}:size=64x64:rate={fps}",
         "-pix_fmt", "yuv420p", "-c:v", "libx264", "-y", str(out)],
        capture_output=True, timeout=120,
    )
    if result.returncode or not out.is_file():
        raise RuntimeError("could not generate fixture clip")
    return out


class DirectorInterfaceTests(unittest.TestCase):
    def test_unknown_role_rejected(self):
        with self.assertRaises(ValueError):
            CreativeDirector("colorist", instructions="x")
        with self.assertRaises(ValueError):
            director_available("colorist")

    def test_roles_cover_template_phases(self):
        self.assertEqual(
            set(ROLE_ROUTES),
            {"creative_direction", "storyboarding", "prompt_compilation",
             "asset_selection", "visual_review", "continuity_review", "revision"},
        )

    def test_unconfigured_router_is_explicit(self):
        with patch.dict(os.environ, {"OMNIROUTE_API_KEY": ""}):
            self.assertFalse(director_available())
            with self.assertRaises(DirectorUnavailable):
                require_director()
            with self.assertRaises(DirectorUnavailable):
                CreativeDirector("storyboarding", instructions="x").run("hi", dict)


class BibleTests(unittest.TestCase):
    def test_default_bible_validates(self):
        validate_bible(default_bible())

    def test_missing_section_rejected(self):
        bible = default_bible()
        del bible["lighting"]
        with self.assertRaises(ValueError):
            validate_bible(bible)

    def test_shot_inheritance(self):
        inherited = inherit_for_shot(default_bible(), {"motion": "slow push"})
        self.assertIn("style", inherited)
        self.assertIn("lighting", inherited)
        self.assertIn("slow push", inherited["motion"])


class RecipeTests(unittest.TestCase):
    def test_ten_recipes_listed(self):
        self.assertEqual(len(motion_recipes.list_recipes()), 10)

    def test_corridor_selects_footage_plus_graphics(self):
        text = CORRIDOR.read_text(encoding="utf-8")
        name, recipe = motion_recipes.select_recipe(text)
        self.assertEqual(name, "footage-plus-graphics")
        self.assertIn("hunyuan_prompt_strategy", recipe)

    def test_ai_selection_falls_back_without_key(self):
        with patch.dict(os.environ, {"OMNIROUTE_API_KEY": ""}):
            choice = motion_recipes.select_recipe_ai("freight corridor shipment record")
        self.assertEqual(choice["source"], "deterministic")
        self.assertIn(choice["recipe"], motion_recipes.RECIPES)


class CinematographyTests(unittest.TestCase):
    def test_fragment_compiles(self):
        fragment = cinematography.describe_shot_language(
            {"shot_type": "wide_establishing", "movement": "push_in", "direction": "", "speed": "slow"},
            {"focal_length": "35mm", "visual_effect": ""},
            {"start": "wide", "end": "hold"},
        )
        self.assertIn("wide establishing", fragment)
        self.assertIn("push in", fragment)
        self.assertIn("35mm", fragment)

    def test_unknown_movement_flagged(self):
        self.assertTrue(cinematography.validate_camera({"movement": "teleport"}))
        self.assertFalse(cinematography.validate_camera({"shot_type": "medium", "movement": "static"}))


class PipelineExtensionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        database = Path(self.temporary.name) / "company.db"
        self.original = (state.DB_PATH, video_store.DB_PATH)
        state.DB_PATH = database
        video_store.DB_PATH = database
        state.init_db()
        video_store.init_video_db()
        self.env = patch.dict(os.environ, {"OMNIROUTE_API_KEY": ""})
        self.env.start()
        self.addCleanup(self.env.stop)

    def tearDown(self):
        state.DB_PATH, video_store.DB_PATH = self.original
        self.temporary.cleanup()

    def test_compiled_prompt_structure(self):
        result = video_pipeline.plan_video(CORRIDOR, project_id="x")
        hunyuan = [shot for shot in result["plan"]["shots"] if shot.get("visualPrompt")]
        self.assertTrue(hunyuan)
        for shot in hunyuan:
            prompt = shot["visualPrompt"]
            for marker in ("Subject:", "Camera:", "Lighting:", "Style:"):
                self.assertIn(marker, prompt)
            self.assertLessEqual(len(prompt), 900)

    def test_t2v_i2v_policy(self):
        result = video_pipeline.plan_video(CORRIDOR, project_id="x")
        modes = {shot["id"]: shot["hunyuan_mode"] for shot in result["plan"]["shots"]}
        # Every shot carries an explicit T2V/I2V decision.
        self.assertTrue(modes)
        self.assertTrue(all(mode in ("t2v", "i2v") for mode in modes.values()))
        # Product/source shots need image references; plain scenery does not.
        self.assertEqual(modes["shot_003"], "i2v")  # IRU source reference
        self.assertEqual(modes["shot_005"], "i2v")  # product record
        self.assertEqual(modes["shot_001"], "t2v")  # open corridor scenery
        # The decision persists onto jobs.
        stored = {job["shotId"]: job["hunyuan_mode"] for job in result["jobs"]}
        self.assertEqual(stored["shot_001"], "t2v")

    def test_shot_record_validation(self):
        result = video_pipeline.plan_video(CORRIDOR, project_id="x")
        spec, plan = result["spec"], result["plan"]
        plan["shots"][0]["camera"]["movement"] = "teleport"
        with self.assertRaises(ValueError):
            video_pipeline.validate_plan(spec, plan)

    def test_asset_registry(self):
        result = video_pipeline.plan_video(CORRIDOR, project_id="x")
        assets = video_store.list_assets(result["spec"]["id"])
        self.assertTrue(assets)
        self.assertTrue(all(asset["path"] for asset in assets))
        referenced = [shot for shot in result["plan"]["shots"] if shot["reference_assets"]]
        self.assertTrue(referenced)

    def test_spec_extra_fields(self):
        parsed = video_pipeline.parse_script(
            "Objective: Prove the record works.\nMessage: One record.\n"
            "Platform: 9:16\nAudio: music\n## 0:00–0:05\nSpoken line.\n",
            source_name="meta.md",
        )
        spec = video_pipeline.build_spec(parsed, project_id="x", context={})
        self.assertEqual(spec["extra"]["objective"], "Prove the record works.")
        self.assertEqual(spec["extra"]["platform"], "9:16")
        self.assertEqual(spec["extra"]["audio"], "music")

    def test_visual_bible_persisted(self):
        result = video_pipeline.plan_video(CORRIDOR, project_id="x")
        bible = video_store.get_visual_bible(result["spec"]["id"])
        self.assertIsNotNone(bible)
        self.assertEqual(bible["recipe_id"], result["recipe"])
        validate_bible(bible["bible"])

    def test_direct_brief_needs_key(self):
        with self.assertRaises(RuntimeError):
            video_pipeline.direct_brief("A 15-second product film.", project_id="x")

    def test_direct_brief_with_faked_director(self):
        creative = video_pipeline.CreativeBriefResponse(
            objective="Show the record.", message="One record.",
            audience="Ops directors", platform="9:16",
            visual_style="cinematic", emotional_direction="confident",
            audio="music", runtime_seconds=12, title="Record film",
        )
        outline = video_pipeline.StoryboardOutline(beats=[
            video_pipeline.StoryboardBeat(
                narration="Trucks move.", visual="Highway freight at dawn.",
                duration_seconds=6.0, purpose="Establish corridor."),
            video_pipeline.StoryboardBeat(
                narration="Records hold.", visual="Documents resolving.",
                duration_seconds=6.0, purpose="Resolve into CTA."),
        ])
        choice = {"source": "ai", "recipe": "footage-plus-graphics", "reason": "test"}
        with patch.object(CreativeDirector, "run", side_effect=[creative, outline]):
            with patch("services.motion_recipes.select_recipe_ai", return_value=choice):
                result = video_pipeline.direct_brief("Trucks and records.", project_id="briefed")
        self.assertEqual(len(result["plan"]["shots"]), 2)
        self.assertEqual(result["spec"]["format"]["durationSeconds"], 12.0)
        self.assertEqual(len(result["jobs"]), 2)
        self.assertEqual(result["plan"]["shots"][0]["transcriptBeatIds"], ["beat_01"])


@unittest.skipUnless(HAS_FFMPEG, "ffmpeg/ffprobe required for review tests")
class ReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.clip = make_clip()

    def _job(self, **overrides):
        job = {"frames": 24, "fps": 24, "width": 64, "height": 64, "seed": 42}
        job.update(overrides)
        return job

    def test_technical_pass(self):
        verdict = review.technical_review(self.clip, self._job())
        self.assertEqual(verdict["status"], "PASS")

    def test_frame_mismatch_regenerates(self):
        verdict = review.technical_review(self.clip, self._job(frames=81))
        self.assertEqual(verdict["status"], "REGENERATE")
        self.assertTrue(verdict["issues"]["critical"])
        self.assertIn("seed", verdict["regeneration_changes"])

    def test_missing_file_is_critical(self):
        verdict = review.technical_review("/nonexistent/x.mp4", self._job())
        self.assertEqual(verdict["status"], "REGENERATE")

    def test_ai_review_abstains_without_key(self):
        with patch.dict(os.environ, {"OMNIROUTE_API_KEY": ""}):
            verdict = review.ai_visual_review(self.clip, {"id": "shot_001"})
        self.assertEqual(verdict["status"], "SKIPPED")

    def test_continuity_chain(self):
        shots = [
            {"id": "shot_001", "continuity": {"nextShot": "shot_002", "style": "s"}},
            {"id": "shot_002", "continuity": {"nextShot": None, "style": "s"}},
        ]
        verdict = review.continuity_review(shots, {
            "shot_001": {"codec": "h264", "fps": 24},
            "shot_002": {"codec": "h264", "fps": 24},
        })
        self.assertEqual(verdict["status"], "PASS")
        verdict = review.continuity_review(shots, {
            "shot_001": {"codec": "h264", "fps": 24},
            "shot_002": {"codec": "hevc", "fps": 30},
        })
        self.assertEqual(verdict["status"], "REVISE")


class QualityGateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        database = Path(self.temporary.name) / "company.db"
        self.original = (state.DB_PATH, video_store.DB_PATH)
        state.DB_PATH = database
        video_store.DB_PATH = database
        state.init_db()
        video_store.init_video_db()
        self.env = patch.dict(os.environ, {"OMNIROUTE_API_KEY": ""})
        self.env.start()
        self.addCleanup(self.env.stop)

    def tearDown(self):
        state.DB_PATH, video_store.DB_PATH = self.original
        self.temporary.cleanup()

    def test_gates_without_artifacts(self):
        result = video_pipeline.plan_video(CORRIDOR, project_id="x")
        report = quality_gates.run_gates(result["spec"], result["plan"], result["jobs"])
        self.assertEqual(report["gates"]["ai_schema"]["status"], "PASS")
        self.assertEqual(report["gates"]["brand"]["status"], "PASS")
        self.assertEqual(report["gates"]["video"]["status"], "SKIPPED")
        self.assertEqual(report["gates"]["assembly"]["status"], "SKIPPED")
        self.assertTrue(report["passed"])

    def test_brand_gate_catches_prohibited_claim(self):
        result = video_pipeline.plan_video(CORRIDOR, project_id="x")
        result["plan"]["shots"][0]["purpose"] = "Guaranteed clearance, 10x faster."
        report = quality_gates.run_gates(result["spec"], result["plan"], result["jobs"])
        self.assertEqual(report["gates"]["brand"]["status"], "FAIL")
        self.assertFalse(report["passed"])


if __name__ == "__main__":
    unittest.main()
