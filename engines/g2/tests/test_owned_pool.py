import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from g2_runtime.media_intelligence import build_media_search_plan, score_media_candidate
from g2_runtime.ingest import load_campaign
from g2_runtime.pool import (
    OwnedPoolProvider,
    PoolClip,
    clip_to_candidate,
    ingest_pool,
    load_pool,
    match_for_scene,
    tag_clips,
    write_pool,
)
from g2_runtime.storyboard import compile_storyboard


ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = ROOT / "fixtures" / "campaign_ready.json"


def _clip(clip_id="owned:abc", **overrides):
    values = {
        "clip_id": clip_id,
        "file": f"{clip_id.replace(':', '_')}.mp4",
        "kind": "product_demo",
        "description": "founder walks through the dispatch board",
        "transcript": "here is how we track every milestone",
        "topics": ["dispatch", "milestones", "demo"],
        "claims": ["claim_milestones"],
        "goals": ["walkthrough"],
        "consent": True,
        "duration_seconds": 12.0,
        "width": 1080,
        "height": 1920,
    }
    values.update(overrides)
    return PoolClip.model_validate(values)


class OwnedPoolTests(unittest.TestCase):
    def test_ingest_registers_prunes_and_keeps_edits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "demo_walkthrough.mp4").write_bytes(b"\x00" * 1024)
            (root / "notes.txt").write_text("not footage")
            pool_path = root / "pool.json"
            first = ingest_pool(root, pool_path)
            self.assertEqual(len(first["added"]), 1)
            self.assertEqual(first["total"], 1)
            clips = load_pool(pool_path)["clips"]
            self.assertEqual(clips[0]["kind"], "broll")
            self.assertFalse(clips[0]["consent"])
            clips[0]["topics"] = ["dispatch"]
            write_pool(clips, pool_path)
            second = ingest_pool(root, pool_path)
            self.assertEqual(second["added"], [])
            self.assertEqual(second["kept"], first["added"])
            self.assertEqual(load_pool(pool_path)["clips"][0]["topics"], ["dispatch"])
            (root / "demo_walkthrough.mp4").unlink()
            third = ingest_pool(root, pool_path)
            self.assertEqual(third["missing_pruned"], first["added"])
            self.assertEqual(third["total"], 0)

    def test_provider_returns_only_consented_matching_video(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("a.mp4", "b.mp4"):
                (root / name).write_bytes(b"\x00" * 64)
            pool_path = root / "pool.json"
            write_pool([
                _clip("owned:a", file="a.mp4").model_dump(mode="json"),
                _clip("owned:b", file="b.mp4", consent=False).model_dump(mode="json"),
            ], pool_path)
            provider = OwnedPoolProvider(pool_path)
            results = provider.search("dispatch milestones demo", 5, "video")
            self.assertEqual([item.candidate_id for item in results], ["owned:a"])
            self.assertEqual(results[0].provider, "owned")
            self.assertEqual(results[0].source_type, "owned")
            self.assertEqual(provider.search("dispatch", 5, "image"), [])
            self.assertEqual(provider.search("unrelated zebra query", 5, "video"), [])

    def test_match_scores_claims_kind_goal_and_consent(self):
        clips = [
            _clip("owned:demo"),
            _clip("owned:face", kind="face", claims=[], topics=["founder", "intro"]),
            _clip("owned:pending", consent=False),
        ]
        matches = match_for_scene(
            clips, purpose="control_system", queries=["dispatch milestones demo"],
            narration="dispatch board milestone tracking", goal="walkthrough",
            claim_ids=["claim_milestones"], duration_seconds=8.0,
            orientation="portrait", minimum_width=1080, minimum_height=1920, limit=3,
        )
        by_id = {item["clip_id"]: item for item in matches}
        self.assertGreater(by_id["owned:demo"]["score"], by_id["owned:face"]["score"])
        self.assertIn("claim grounded on camera: claim_milestones", by_id["owned:demo"]["reasons"])
        self.assertIn("campaign goal match", by_id["owned:demo"]["reasons"])
        self.assertEqual(by_id["owned:pending"]["score"], 0.0)
        self.assertIn("consent", by_id["owned:pending"]["reasons"][0])

    def test_match_prefers_face_for_cover(self):
        clips = [
            _clip("owned:demo"),
            _clip("owned:face", kind="face", claims=[], topics=["cover", "intro"]),
        ]
        matches = match_for_scene(
            clips, purpose="cover", queries=["cover intro"], narration="cover intro",
            goal="awareness", claim_ids=[], duration_seconds=5.0, limit=2,
        )
        self.assertEqual(matches[0]["clip_id"], "owned:face")

    def test_tag_clips_updates_untagged_and_filters_claims(self):
        class FakeModel:
            configured = True

            def complete_json(self, system, user):
                return {"kind": "face", "topics": ["Founder Intro"], "claims": ["claim_x", "claim_other"],
                        "goals": ["awareness", "bogus"], "speaker": "Jane", "description": "Founder intro."}

        with tempfile.TemporaryDirectory() as tmp:
            pool_path = Path(tmp) / "pool.json"
            write_pool([_clip("owned:t", topics=[], claims=[]).model_dump(mode="json")], pool_path)
            result = tag_clips(pool_path, model=FakeModel(), claim_ids=["claim_x"])
            self.assertEqual(result["tagged"], ["owned:t"])
            clip = load_pool(pool_path)["clips"][0]
            self.assertEqual(clip["kind"], "face")
            self.assertEqual(clip["claims"], ["claim_x"])
            self.assertEqual(clip["goals"], ["awareness"])
            rerun = tag_clips(pool_path, model=FakeModel(), claim_ids=["claim_x"])
            self.assertEqual(rerun["tagged"], [])
            self.assertEqual(rerun["skipped"], ["owned:t"])

    def test_tag_clips_requires_configured_model(self):
        class DeadModel:
            configured = False

        with tempfile.TemporaryDirectory() as tmp:
            pool_path = Path(tmp) / "pool.json"
            write_pool([], pool_path)
            with self.assertRaises(RuntimeError):
                tag_clips(pool_path, model=DeadModel())

    def test_owned_candidate_flows_through_federated_scoring(self):
        campaign = load_campaign(CAMPAIGN)
        storyboard = compile_storyboard(campaign, 45)
        plan = build_media_search_plan(campaign, storyboard)
        requirement = next(item for item in plan.requirements if item.purpose == "evidence")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "dispatch.mp4").write_bytes(b"\x00" * 64)
            candidate = clip_to_candidate(
                _clip("owned:dispatch", file="dispatch.mp4", topics=["document", "paperwork"]),
                root, query="shipping documents desk close up")
            scored = score_media_candidate(candidate, requirement)
            self.assertGreater(scored.score, 0.0)

    def test_ingest_rejects_missing_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                ingest_pool(Path(tmp) / "nope", Path(tmp) / "pool.json")


if __name__ == "__main__":
    unittest.main()
