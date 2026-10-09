"""QA gate: a render either passes every check or explains why it failed."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from services.video.qa_gate import run_qa_gate

HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
CANVAS = (320, 400)


def make_clip(destination: Path, duration: float, *, audio: bool = False) -> Path:
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi",
        "-i", f"testsrc=duration={duration}:size={CANVAS[0]}x{CANVAS[1]}:rate=24",
    ]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"anullsrc=duration={duration}:r=44100"]
    cmd += ["-pix_fmt", "yuv420p", "-c:v", "libx264"]
    if audio:
        cmd += ["-c:a", "aac", "-shortest"]
    cmd += [str(destination)]
    subprocess.run(cmd, capture_output=True, timeout=120, check=True)
    return destination


@unittest.skipUnless(HAS_FFMPEG, "ffmpeg is required")
class QAGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp(prefix="qa-"))
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.clip = make_clip(self.dir / "beat_01.mp4", 5.0)

    def shots(self) -> list[dict]:
        return [
            {"n": 1, "path": str(self.clip), "t_in": 0.0, "t_out": 5.0,
             "caption_lines": []},
        ]

    def gate(self, **kwargs) -> dict:
        args = {
            "shots": self.shots(),
            "canvas": CANVAS,
            "source_text": "MANY BORDERS.",
            "output_dir": self.dir / "report",
        }
        args.update(kwargs)
        return run_qa_gate(**args)

    def test_silent_render_passes_when_audio_not_required(self):
        """Regression: SKIPPED audio used to fail an otherwise clean gate."""
        report = self.gate()
        self.assertEqual(report["checks"]["audio"]["status"], "SKIPPED")
        self.assertTrue(report["passed"], report["checks"])

    def test_missing_audio_fails_when_required(self):
        report = self.gate(require_audio=True)
        self.assertEqual(report["checks"]["audio"]["status"], "FAIL")
        self.assertFalse(report["passed"])

    def test_missing_shot_fails_loudly(self):
        report = self.gate(shots=[
            {"n": 1, "path": str(self.dir / "absent.mp4"),
             "t_in": 0.0, "t_out": 5.0, "caption_lines": []},
        ])
        self.assertEqual(report["checks"]["shots_present"]["status"], "FAIL")
        self.assertFalse(report["passed"])

    def test_geometry_mismatch_fails(self):
        report = self.gate(canvas=(1080, 1350))
        self.assertEqual(report["checks"]["geometry"]["status"], "FAIL")
        self.assertFalse(report["passed"])


if __name__ == "__main__":
    unittest.main()
