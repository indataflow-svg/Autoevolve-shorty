"""Assembly invariants: ordering, refusal to assemble partial or bad chunks."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from services.video import assembly

HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def make_mp4(path: Path, *, frames: int = 30, fps: int = 24, size: str = "64x64") -> int:
    """Write an MP4 with an exact frame count; return what ffprobe reads back."""
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"testsrc=duration={frames / fps}:size={size}:rate={fps}",
            "-pix_fmt", "yuv420p", "-c:v", "libx264", str(path),
        ],
        capture_output=True,
        timeout=120,
        check=True,
    )
    return assembly.probe_frame_count(path) or 0


def chunk_job(path: Path, index: int, *, status: str = "completed",
              declared_frames: int | None = None, actual_frames: int | None = None) -> dict:
    return {
        "id": f"job_{index:03d}",
        "shot_id": f"chunk_{index:02d}",
        "status": status,
        "result": {
            "outputPath": str(path),
            "frames": declared_frames if declared_frames is not None else actual_frames,
        },
    }


class ChunkOrderingTests(unittest.TestCase):
    def test_order_is_derived_from_persisted_shot_id(self):
        self.assertEqual(assembly.chunk_order({"shot_id": "chunk_01"}), 0)
        self.assertEqual(assembly.chunk_order({"shot_id": "chunk_12"}), 11)
        # Store rows use snake_case; built jobs use camelCase.
        self.assertEqual(assembly.chunk_order({"shotId": "chunk_07"}), 6)

    def test_non_chunk_is_rejected(self):
        with self.assertRaises(assembly.AssemblyError):
            assembly.chunk_order({"shot_id": "shot_003"})

    def test_plan_chunks_sorts_and_contiguity_is_enforced(self):
        jobs = [{"shot_id": f"chunk_{i:02d}"} for i in (3, 1, 2)]
        self.assertEqual(
            [job["shot_id"] for job in assembly.plan_chunks(jobs)],
            ["chunk_01", "chunk_02", "chunk_03"],
        )
        with self.assertRaises(assembly.AssemblyError):
            assembly.plan_chunks([{"shot_id": "chunk_01"}, {"shot_id": "chunk_03"}])


@unittest.skipUnless(HAS_FFMPEG, "ffmpeg/ffprobe required")
class CompletedChunkTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="assembly-"))

    def _chunks(self, count: int = 3, **kwargs) -> list[dict]:
        jobs = []
        for index in range(1, count + 1):
            path = self.dir / f"chunk_{index:02d}.mp4"
            actual = make_mp4(path, frames=kwargs.get("frames", 30))
            jobs.append(chunk_job(path, index, actual_frames=actual))
        return jobs

    def test_completed_paths_in_order(self):
        jobs = self._chunks(3)
        paths = assembly.completed_chunk_paths(jobs)
        self.assertEqual([p.name for p in paths], [f"chunk_{i:02d}.mp4" for i in (1, 2, 3)])

    def test_pending_chunk_blocks_assembly(self):
        jobs = self._chunks(2)
        jobs[1]["status"] = "pending"
        with self.assertRaises(assembly.AssemblyError) as caught:
            assembly.completed_chunk_paths(jobs)
        self.assertIn("not completed", str(caught.exception))

    def test_declared_frame_mismatch_is_refused(self):
        # A job row must never be able to smuggle a truncated artifact into a
        # finished video: the file's own frame count wins.
        jobs = self._chunks(2)
        jobs[1]["result"]["frames"] = 999
        with self.assertRaises(assembly.AssemblyError) as caught:
            assembly.completed_chunk_paths(jobs)
        self.assertIn("declares 999 frames", str(caught.exception))

    def test_missing_file_is_refused(self):
        jobs = self._chunks(1)
        jobs[0]["result"]["outputPath"] = str(self.dir / "gone.mp4")
        with self.assertRaises(assembly.AssemblyError):
            assembly.completed_chunk_paths(jobs)


@unittest.skipUnless(HAS_FFMPEG, "ffmpeg/ffprobe required")
class AssembleFullVideoTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="assembly-"))

    def _chunks(self, frames: int = 30, count: int = 3) -> list[dict]:
        jobs = []
        for index in range(1, count + 1):
            path = self.dir / f"chunk_{index:02d}.mp4"
            actual = make_mp4(path, frames=frames)
            jobs.append(chunk_job(path, index, actual_frames=actual))
        return jobs

    def test_concatenates_into_one_deliverable(self):
        jobs = self._chunks(frames=30, count=3)
        out = self.dir / "nested" / "full.mp4"
        report = assembly.assemble_full_video(jobs, out)
        self.assertTrue(out.is_file())
        self.assertEqual(report["chunks"], 3)
        self.assertEqual(report["frames"], 90)
        self.assertAlmostEqual(report["duration_seconds"], 90 / 24, places=1)
        self.assertEqual(len(report["sha256"]), 64)
        # The concat listing must not be left behind.
        self.assertFalse(out.with_suffix(".concat.txt").exists())

    def test_mismatched_chunk_geometry_is_refused(self):
        jobs = self._chunks(frames=30, count=2)
        odd = self.dir / "chunk_02.mp4"
        make_mp4(odd, frames=30, size="32x32")
        with self.assertRaises(assembly.AssemblyError) as caught:
            assembly.assemble_full_video(jobs, self.dir / "full.mp4")
        self.assertIn("stream copy", str(caught.exception))

    def test_incomplete_plan_never_produces_a_file(self):
        jobs = self._chunks(count=2)
        jobs[0]["status"] = "pending"
        out = self.dir / "full.mp4"
        with self.assertRaises(assembly.AssemblyError):
            assembly.assemble_full_video(jobs, out)
        self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
