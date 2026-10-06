"""Deterministic footage rendering: trim, crop, scale, zoom/pan.

Real footage is never generated -- it is cut to the beat window, cropped by
the focus hint, scaled to the canvas, and optionally moved with an eased
zoom/pan from the beat's motion list. One filtergraph, one encode per shot.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any


class FootageError(RuntimeError):
    """Raised when a footage shot cannot be rendered."""


def has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def crop_x_expression(focus: str) -> str:
    """Horizontal anchor for the cover-crop, from the focus hint."""
    focus = (focus or "centre").strip().lower()
    if focus == "left":
        return "0"
    if focus == "right":
        return "(in_w-out_w)"
    return "(in_w-out_w)/2"


def zoompan_filter(
    motion: list[str], duration: float, canvas: tuple[int, int], fps: int = 24
) -> str:
    """Eased zoom/pan from the motion list, or empty for a static shot."""
    text = " ".join(motion or []).lower()
    frames = max(1, round(duration * fps))
    width, height = canvas
    # zoompan's s= is the OUTPUT size (the canvas), d= is the frame count.
    if "push in" in text or "zoom in" in text:
        return (
            f"zoompan=z='min(zoom+0.0008,1.08)':d={frames}:x='iw/2-(iw/zoom/2)'"
            f":y='ih/2-(ih/zoom/2)':s={width}x{height}:fps={fps}"
        )
    if "pull out" in text or "zoom out" in text:
        return (
            f"zoompan=z='max(zoom-0.0008,1.0)':d={frames}:x='iw/2-(iw/zoom/2)'"
            f":y='ih/2-(ih/zoom/2)':s={width}x{height}:fps={fps}"
        )
    if "pan" in text:
        direction = -1 if "left" in text else 1
        return (
            f"zoompan=z=1.05:d={frames}:x='(iw-iw/zoom)*on/{frames}*{direction}'"
            f":y='ih/2-(ih/zoom/2)':s={width}x{height}:fps={fps}"
        )
    return ""


def render_footage(
    source: str | Path,
    destination: str | Path,
    *,
    t_in: float,
    t_out: float,
    canvas: tuple[int, int],
    focus: str = "centre",
    motion: list[str] | None = None,
    fps: int = 24,
) -> dict[str, Any]:
    """Cut `source` to the beat window and frame it on the canvas.

    Cover-crop anchored at the focus hint, scale to canvas, optional eased
    move. The output duration equals the beat window; anything else is a
    failure, not a near-miss.
    """
    if not has_ffmpeg():
        raise FootageError("ffmpeg is required to render footage")
    src = Path(source)
    if not src.is_file():
        raise FootageError(f"source footage is missing: {src}")
    duration = t_out - t_in
    if duration <= 0:
        raise FootageError(f"beat window is not positive: {t_in}-{t_out}")
    width, height = canvas

    filters = [
        f"scale={width}:{height}:force_original_aspect_ratio=increase",
        f"crop={width}:{height}:x={crop_x_expression(focus)}:y=(in_h-out_h)/2",
    ]
    move = zoompan_filter(motion or [], duration, (width, height), fps)
    if move:
        filters.append(move)
    filters.append(f"fps={fps}")
    filters.append("format=yuv420p")

    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{t_in:.3f}", "-i", str(src),
            "-t", f"{duration:.3f}",
            "-vf", ",".join(filters),
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-movflags", "+faststart",
            str(target),
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.returncode or not target.is_file() or target.stat().st_size <= 0:
        raise FootageError(
            f"footage render failed: {(result.stderr or '').strip()[-400:]}"
        )
    return {
        "output_path": str(target),
        "duration_seconds": round(duration, 3),
        "canvas": [width, height],
        "focus": focus,
        "motion": list(motion or []),
        "file_size_bytes": target.stat().st_size,
    }
