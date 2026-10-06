"""Pack parsing: structure, byte-exact captions, and GPU eligibility."""
from __future__ import annotations

import unittest
from pathlib import Path

from services.video.md_pack import (
    PackError,
    beats_json,
    format_timestamp,
    load_pack,
    parse_pack,
    parse_timestamp,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "corridor-pack.md"


class TimestampTests(unittest.TestCase):
    def test_minute_second_and_hour_forms(self):
        self.assertEqual(parse_timestamp("0:06"), 6.0)
        self.assertEqual(parse_timestamp("1:02:03"), 3723.0)
        self.assertEqual(parse_timestamp("0:49"), 49.0)

    def test_bad_timestamps_are_rejected(self):
        for value in ("abc", "1:60", "99", "1:2:3:4", ""):
            with self.assertRaises(PackError, msg=value):
                parse_timestamp(value)

    def test_format_round_trips(self):
        for seconds in (0.0, 6.0, 49.0, 3723.0):
            self.assertEqual(parse_timestamp(format_timestamp(seconds)), seconds)


class ParsePackTests(unittest.TestCase):
    def setUp(self):
        self.concepts = load_pack(FIXTURE)

    def test_one_concept_with_six_beats(self):
        self.assertEqual(len(self.concepts), 1)
        concept = self.concepts[0]
        self.assertEqual(concept.n, 1)
        self.assertEqual(concept.title, "One shipment, many borders")
        self.assertEqual(concept.buyer, "freight operations lead")
        self.assertEqual(concept.target_duration, 49.0)
        self.assertEqual(len(concept.beats), 6)

    def test_timestamps_are_contiguous_and_cover_the_target(self):
        beats = self.concepts[0].beats
        self.assertEqual(beats[0].t_in, 0.0)
        self.assertEqual(beats[-1].t_out, 49.0)
        for previous, current in zip(beats, beats[1:]):
            self.assertEqual(current.t_in, previous.t_out)

    def test_captions_are_byte_exact_from_the_markdown(self):
        """No caption may be invented, reworded or trimmed."""
        source = FIXTURE.read_text(encoding="utf-8")
        for beat in self.concepts[0].beats:
            self.assertTrue(beat.caption_lines, f"beat {beat.n} has no captions")
            for line in beat.caption_lines:
                self.assertIn(line, source, f"caption not in source: {line!r}")

    def test_caption_count_matches_the_source(self):
        concept = self.concepts[0]
        self.assertEqual(len(concept.beats[0].caption_lines), 3)
        self.assertEqual(len(concept.beats[1].caption_lines), 4)
        self.assertEqual(len(concept.beats[5].caption_lines), 3)

    def test_fields_are_mapped(self):
        beat = self.concepts[0].beats[0]
        self.assertEqual(beat.preferred_type, "cinematic generated opener")
        self.assertEqual(beat.search, "container corridor dawn aerial")
        self.assertEqual(beat.crop_focus, "centre")
        self.assertEqual(beat.motion, ["slow push in"])
        self.assertIn("flat vector illustration", beat.fallback_prompt)

    def test_gpu_eligibility_requires_type_and_prompt(self):
        beats = {beat.n: beat for beat in self.concepts[0].beats}
        # Generated type + a real fallback prompt -> GPU.
        self.assertTrue(beats[1].generate)
        # "Not needed" means deterministic, whatever the type says.
        for n in (2, 3, 4, 5, 6):
            self.assertFalse(beats[n].generate, f"beat {n} should be deterministic")

    def test_beats_json_reports_gpu_count(self):
        report = beats_json(self.concepts)
        self.assertEqual(report["total_duration"], 49.0)
        self.assertEqual(report["gpu_beats"], 1)
        self.assertEqual(len(report["concepts"][0]["beats"]), 6)


class PackValidationTests(unittest.TestCase):
    def test_empty_pack_is_rejected(self):
        with self.assertRaises(PackError):
            parse_pack("")
        with self.assertRaises(PackError):
            parse_pack("   \n\n  ")

    def test_missing_concept_sections_is_rejected(self):
        with self.assertRaises(PackError):
            parse_pack("# Title\n\nSome prose with no concept heading.\n")

    def test_transcript_sourcing_count_mismatch_is_rejected(self):
        text = FIXTURE.read_text(encoding="utf-8")
        # Drop one sourcing beat block.
        broken = text.replace("**Beat 6 — CTA**", "**Beat 6x — CTA**")
        with self.assertRaises(PackError) as caught:
            parse_pack(broken)
        self.assertIn("must match one to one", str(caught.exception))

    def test_timestamp_gap_is_rejected(self):
        text = FIXTURE.read_text(encoding="utf-8")
        broken = text.replace("**0:06–0:14 — Problem**", "**0:07–0:14 — Problem**")
        with self.assertRaises(PackError) as caught:
            parse_pack(broken)
        self.assertIn("gap", str(caught.exception))

    def test_timestamp_overlap_is_rejected(self):
        text = FIXTURE.read_text(encoding="utf-8")
        broken = text.replace("**0:06–0:14 — Problem**", "**0:05–0:14 — Problem**")
        with self.assertRaises(PackError) as caught:
            parse_pack(broken)
        self.assertIn("before beat", str(caught.exception))

    def test_duration_mismatch_is_rejected(self):
        text = FIXTURE.read_text(encoding="utf-8")
        broken = text.replace("Target duration: 0:49", "Target duration: 0:50")
        with self.assertRaises(PackError) as caught:
            parse_pack(broken)
        self.assertIn("does not match", str(caught.exception))

    def test_missing_target_duration_is_rejected(self):
        text = FIXTURE.read_text(encoding="utf-8")
        broken = text.replace("Target duration: 0:49\n", "")
        with self.assertRaises(PackError) as caught:
            parse_pack(broken)
        self.assertIn("target duration", str(caught.exception))

    def test_concept_numbers_must_be_ordered(self):
        text = FIXTURE.read_text(encoding="utf-8")
        broken = text.replace("## 1. One shipment", "## 2. One shipment")
        with self.assertRaises(PackError) as caught:
            parse_pack(broken)
        self.assertIn("1..n", str(caught.exception))

    def test_sourcing_beats_must_be_ordered(self):
        text = FIXTURE.read_text(encoding="utf-8")
        broken = text.replace("**Beat 2 — Problem**", "**Beat 9 — Problem**")
        with self.assertRaises(PackError) as caught:
            parse_pack(broken)
        self.assertIn("out of order", str(caught.exception))


class MultiConceptTests(unittest.TestCase):
    def test_second_concept_parses(self):
        text = FIXTURE.read_text(encoding="utf-8")
        extra = text + (
            "\n## 2. A second concept\n\n"
            "Buyer: ops lead\n"
            "Target duration: 0:10\n\n"
            "**0:00–0:10 — Only**\n"
            "A single caption line.\n\n"
            "**Beat 1 — Only**\n"
            "- Visible: something\n"
            "- Preferred visual type: stock footage\n"
            "- Search: containers\n"
            "- Portrait crop: centre\n"
            "- Motion: static\n"
            "- Connection: none\n"
            "- Fallback generated-image prompt: Not needed\n"
        )
        concepts = parse_pack(extra)
        self.assertEqual(len(concepts), 2)
        self.assertEqual(concepts[1].n, 2)
        self.assertEqual(concepts[1].target_duration, 10.0)
        self.assertEqual(concepts[1].beats[0].caption_lines, ["A single caption line."])
        self.assertFalse(concepts[1].beats[0].generate)


if __name__ == "__main__":
    unittest.main()
