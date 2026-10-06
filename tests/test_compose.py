"""Compose registration: pack concepts become specs, plans and GPU jobs."""
from __future__ import annotations

import unittest
from pathlib import Path

from services.video.compose import gpu_jobs_for_concept, register_pack_concept
from services.video.md_pack import Beat, Concept, load_pack

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "corridor-pack.md"


def concept() -> Concept:
    return load_pack(FIXTURE)[0]


class RegisterPackConceptTests(unittest.TestCase):
    def test_registers_spec_plan_and_all_six_shots(self):
        reg = register_pack_concept(concept(), project_id="test-pack")
        self.assertTrue(reg["spec"]["id"])
        self.assertEqual(reg["plan"]["video_spec_id"], reg["spec"]["id"])
        self.assertEqual(len(reg["plan"]["shots"]), 6)
        self.assertEqual(reg["plan"]["total_duration_seconds"], 49.0)

    def test_transcript_captions_survive_registration_verbatim(self):
        """Captions are never reworded on the way into the plan."""
        source = FIXTURE.read_text(encoding="utf-8")
        reg = register_pack_concept(concept(), project_id="test-pack")
        for shot in reg["plan"]["shots"]:
            self.assertTrue(shot["caption_lines"], shot["id"])
            for line in shot["caption_lines"]:
                self.assertIn(line, source)

    def test_routing_verdict_is_stored_per_shot(self):
        """The pack's Preferred visual type routes first; the verdict is kept."""
        reg = register_pack_concept(concept(), project_id="test-pack")
        by_id = {shot["id"]: shot for shot in reg["plan"]["shots"]}
        # Beat 1 is the generated opener: hunyuan renderer, render-required.
        # (Its type is "mixed" because freight cues also match stock; the
        # renderer verdict is what the GPU gate reads.)
        self.assertEqual(by_id["beat_01"]["renderer"], "hunyuan")
        self.assertIn("hunyuan", by_id["beat_01"]["families"])
        self.assertTrue(by_id["beat_01"]["renderRequired"])
        # Deterministic beats are typed for their compose renderer, never
        # hunyuan, and never render-required on GPU.
        for shot_id in ("beat_02", "beat_03", "beat_04", "beat_05", "beat_06"):
            shot = by_id[shot_id]
            self.assertNotEqual(shot["visualType"], "hunyuan", shot_id)
            self.assertFalse(shot["renderRequired"], shot_id)
            self.assertTrue(shot["families"], shot_id)

    def test_gpu_beat_carries_the_fallback_prompt(self):
        reg = register_pack_concept(concept(), project_id="test-pack")
        shot = next(s for s in reg["plan"]["shots"] if s["id"] == "beat_01")
        self.assertIn("flat vector illustration", shot["visualPrompt"])


class GpuJobsTests(unittest.TestCase):
    def test_gpu_off_yields_zero_jobs(self):
        """No beat with generate=false may ever become a Hunyuan job."""
        reg = register_pack_concept(concept(), project_id="test-pack")
        jobs = gpu_jobs_for_concept(
            concept(), project_id="test-pack",
            spec_id=reg["spec"]["id"], plan_id=reg["plan"]["id"],
        )
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["shotId"], "beat_01")
        self.assertEqual(jobs[0]["frames"], 144)
        self.assertEqual(jobs[0]["renderer"], "hunyuan")

    def test_concept_with_no_generate_beats_yields_zero_jobs(self):
        calm = Concept(n=9, title="All deterministic", buyer="x", target_duration=10.0)
        calm.beats.append(Beat(
            n=1, t_in=0.0, t_out=10.0, caption_lines=["HELLO."],
            visible="A timeline builds left to right",
            preferred_type="motion graphics timeline",
            fallback_prompt="Not needed", generate=False,
        ))
        reg = register_pack_concept(calm, project_id="test-pack")
        jobs = gpu_jobs_for_concept(
            calm, project_id="test-pack",
            spec_id=reg["spec"]["id"], plan_id=reg["plan"]["id"],
        )
        self.assertEqual(jobs, [])

    def test_generate_beat_routed_off_hunyuan_yields_zero_jobs(self):
        """A generate flag pointing at a deterministic draw must not reach GPU."""
        tricky = Concept(n=9, title="Tricky", buyer="x", target_duration=10.0)
        tricky.beats.append(Beat(
            n=1, t_in=0.0, t_out=10.0, caption_lines=["HELLO."],
            visible="An icon of connected nodes",
            preferred_type="generated illustration title",
            fallback_prompt="Flat vector illustration of connected nodes",
            generate=True,
        ))
        reg = register_pack_concept(tricky, project_id="test-pack")
        shots = reg["plan"]["shots"]
        self.assertNotEqual(shots[0]["visualType"], "hunyuan")
        jobs = gpu_jobs_for_concept(
            tricky, project_id="test-pack",
            spec_id=reg["spec"]["id"], plan_id=reg["plan"]["id"],
        )
        self.assertEqual(jobs, [])


if __name__ == "__main__":
    unittest.main()
