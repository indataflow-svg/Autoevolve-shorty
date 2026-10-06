"""Ingest: pack parsing at the boundary, media validation, and refusal paths."""
from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from services.video.ingest import (
    IngestError,
    ingest_dir,
    probe_media,
    store_media,
    store_pack,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "corridor-pack.md"


def make_mp4(path: Path, *, frames: int = 24, size: str = "320x240") -> None:
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i",
            f"testsrc=duration={frames / 24}:size={size}:rate=24",
            "-pix_fmt", "yuv420p", "-c:v", "libx264", str(path),
        ],
        capture_output=True,
        timeout=120,
        check=True,
    )


class StorePackTests(unittest.TestCase):
    def test_pack_is_stored_and_parsed(self):
        report = store_pack("proj-pack", "scenario.md", FIXTURE.read_bytes())
        self.assertEqual(report["size_bytes"], FIXTURE.stat().st_size)
        self.assertEqual(len(report["concepts"]), 1)
        self.assertEqual(report["total_duration"], 49.0)
        self.assertEqual(report["gpu_beats"], 1)
        self.assertEqual(len(report["sha256"]), 64)
        stored = Path(report["path"])
        self.assertTrue(stored.is_file())
        # The stored bytes are the uploaded bytes, unchanged.
        self.assertEqual(stored.read_bytes(), FIXTURE.read_bytes())

    def test_non_markdown_pack_is_rejected(self):
        with self.assertRaises(IngestError) as caught:
            store_pack("proj", "scenario.exe", b"MZ")
        self.assertIn("must be markdown", str(caught.exception))

    def test_malformed_pack_is_rejected_with_reason(self):
        with self.assertRaises(IngestError) as caught:
            store_pack("proj", "bad.md", b"## 1. X\n\nno timed beats here\n")
        self.assertIn("pack rejected", str(caught.exception))

    def test_oversized_pack_is_rejected(self):
        with self.assertRaises(IngestError):
            store_pack("proj", "big.md", b"x" * 3_000_000)

    def test_unsafe_project_id_is_rejected(self):
        for project_id in ("..", "a/b", "a\\b", "."):
            with self.assertRaises(IngestError, msg=project_id):
                ingest_dir(project_id)


class StoreMediaTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="ingest-test-"))

    def test_valid_media_is_probed_and_described(self):
        source = self.dir / "clip.mp4"
        make_mp4(source, frames=48)
        data = source.read_bytes()
        report = store_media("proj-media", "clip.mp4", data)
        self.assertEqual(report["type"], "founder_footage")
        self.assertEqual(report["duration_seconds"], 2.0)
        self.assertEqual(report["width"], 320)
        self.assertEqual(report["height"], 240)
        self.assertEqual(report["codec"], "h264")
        self.assertEqual(report["size_bytes"], len(data))
        # Original bytes unchanged.
        self.assertEqual(Path(report["path"]).read_bytes(), data)

    def test_explicit_tag_overrides_suffix_type(self):
        source = self.dir / "clip.mp4"
        make_mp4(source, frames=24)
        report = store_media("proj", "clip.mp4", source.read_bytes(), tag="ui_capture")
        self.assertEqual(report["type"], "ui_capture")

    def test_unsupported_suffix_is_rejected(self):
        with self.assertRaises(IngestError) as caught:
            store_media("proj", "notes.txt", b"hello")
        self.assertIn("unsupported media type", str(caught.exception))

    def test_truncated_media_is_rejected_and_cleaned_up(self):
        """A partial upload must not reach the compose stage."""
        good = self.dir / "good.mp4"
        make_mp4(good, frames=24)
        truncated = good.read_bytes()[: len(good.read_bytes()) // 2]
        with self.assertRaises(IngestError):
            store_media("proj-truncated", "truncated.mp4", truncated)
        # Nothing is left behind for a later render to pick up.
        self.assertEqual(
            [p for p in Path(ingest_dir("proj-truncated")).iterdir() if p.suffix == ".mp4"],
            [],
        )

    def test_empty_file_is_rejected(self):
        with self.assertRaises(IngestError):
            store_media("proj", "empty.mp4", b"")


class ProbeMediaTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="probe-test-"))

    def test_non_media_file_is_rejected(self):
        target = self.dir / "fake.mp4"
        target.write_bytes(b"not a video at all")
        with self.assertRaises(IngestError) as caught:
            probe_media(target)
        self.assertIn("unreadable media file", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
