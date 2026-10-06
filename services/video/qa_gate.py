"""QA gate: a render fails if any check fails.

Runs after a video is assembled and produces a machine-readable report plus a
contact sheet (one frame per beat) for human review. The gate is deliberately
strict: a shot that is the wrong length, the wrong size, or missing its audio
fails the render rather than shipping a near-miss.

Caption text is checked against the source pack byte for byte, because a
caption that has been reworded or trimmed is a claim change, not a styling
choice.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

# How far a shot's duration may drift from its beat window before it fails.
DURATION_TOLERANCE_SECONDS = 0.5
# Contact sheet layout.
SHEET_COLUMNS = 3


class QAGateError(RuntimeError):
    """Raised when the QA gate cannot run at all (missing ffmpeg, bad input)."""


def has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def probe_clip(path: str | Path) -> dict[str, Any]:
    """ffprobe one clip: codec, geometry, frame rate, duration, audio."""
    if not has_ffmpeg():
        raise QAGateError("ffmpeg/ffprobe are required for the QA gate")
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries",
            "format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate",
            "-of", "json", str(path),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode:
        raise QAGateError(
            f"ffprobe failed on {path}: {(result.stderr or '').strip()[-300:]}"
        )
    try:
        payload = json.loads(result.stdout or "{}")
    except ValueError as exc:
        raise QAGateError(f"ffprobe returned non-JSON for {path}") from exc

    video = next(
        (
            stream for stream in (payload.get("streams") or [])
            if stream.get("codec_type") == "video"
        ),
        {},
    )
    audio = [
        stream for stream in (payload.get("streams") or [])
        if stream.get("codec_type") == "audio"
    ]
    if not video:
        raise QAGateError(f"no video stream in {path}")
    rate = str(video.get("avg_frame_rate") or "0/1")
    numerator, _, denominator = rate.partition("/")
    try:
        fps = float(numerator) / float(denominator or 1)
    except (ValueError, ZeroDivisionError):
        fps = 0.0
    try:
        duration = float((payload.get("format") or {}).get("duration") or 0.0)
    except (TypeError, ValueError) as exc:
        raise QAGateError(f"unreadable duration for {path}") from exc
    return {
        "codec": video.get("codec_name"),
        "width": video.get("width"),
        "height": video.get("height"),
        "fps": fps,
        "duration_seconds": round(duration, 3),
        "has_audio": bool(audio),
    }


def extract_frame(clip: str | Path, at_seconds: float, destination: str | Path) -> Path:
    """Grab one frame from a clip for the contact sheet."""
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{max(0.0, at_seconds):.3f}", "-i", str(clip),
            "-frames:v", "1", "-q:v", "3", str(target),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode or not target.is_file():
        raise QAGateError(
            f"could not extract a frame from {clip}: "
            f"{(result.stderr or '').strip()[-300:]}"
        )
    return target


def build_contact_sheet(
    frames: list[Path], destination: str | Path, *, columns: int = SHEET_COLUMNS,
    label: str = "",
) -> Path:
    """Tile per-beat frames into one review image.

    A contact sheet is the cheapest way to review a whole video: one glance
    shows whether every beat landed, whether the grade is consistent and whether
    any frame is broken.
    """
    if not frames:
        raise QAGateError("no frames to build a contact sheet from")
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    streams = "".join(f"-i {frame} " for frame in frames)
    # Pad to a whole number of rows with the last frame, then tile.
    rows = (len(frames) + columns - 1) // columns
    padded = list(frames)
    if len(padded) < rows * columns and padded:
        padded = padded + [padded[-1]] * (rows * columns - len(padded))
    filter_graph = (
        f"{''.join(f'[{index}:v]scale=320:-1[v{index}];' for index in range(len(padded)))}"
        f"{''.join(f'[v{index}]' for index in range(len(padded)))}"
        f"xstack=inputs={len(padded)}:layout={''.join(f'{index % columns}_{index // columns}|' for index in range(len(padded)))}"
    )
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        *[part for frame in padded for part in ("-i", str(frame))],
        "-filter_complex", filter_graph, "-frames:v", "1", str(target),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=300)
    if result.returncode or not target.is_file():
        raise QAGateError(
            f"contact sheet failed: {(result.stderr or '').strip()[-400:]}"
        )
    return target


def check_caption_grounding(
    beats: list[dict[str, Any]], source_text: str
) -> list[str]:
    """Every caption line must appear in the source pack byte for byte."""
    failures: list[str] = []
    for beat in beats:
        for line in beat.get("caption_lines") or []:
            if line not in source_text:
                failures.append(f"beat {beat.get('n')}: caption not in source: {line!r}")
    return failures


def run_qa_gate(
    shots: list[dict[str, Any]],
    *,
    canvas: tuple[int, int],
    source_text: str,
    output_dir: str | Path,
    require_audio: bool = False,
) -> dict[str, Any]:
    """Run every check. Returns a report; ``passed`` is only true if all pass.

    ``shots`` entries carry ``path``, ``t_in``, ``t_out`` and ``n``. A shot
    whose file is missing fails immediately rather than being skipped, so a
    render can never be declared good while a beat is absent.
    """
    if not has_ffmpeg():
        raise QAGateError("ffmpeg/ffprobe are required for the QA gate")
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)

    checks: dict[str, Any] = {}
    frames: list[Path] = []

    # 1. Every shot exists and probes.
    probes: list[dict[str, Any]] = []
    missing = [shot["n"] for shot in shots if not Path(shot["path"]).is_file()]
    if missing:
        checks["shots_present"] = {
            "status": "FAIL",
            "reason": f"missing shot files: {missing}",
        }
        return _report(checks, directory, frames, passed=False)
    checks["shots_present"] = _pass(f"{len(shots)} shot files present")

    for shot in shots:
        probe = probe_clip(shot["path"])
        probes.append({"n": shot["n"], **probe})
        # The shot file spans only its own window, so the frame is taken from
        # the middle of the file rather than the middle of the timeline.
        frames.append(
            extract_frame(shot["path"], (shot["t_out"] - shot["t_in"]) / 2,
                          directory / f"frame_{shot['n']}.jpg")
        )
    checks["probe"] = _pass("every shot decodes")

    # 2. Geometry matches the canvas.
    width, height = canvas
    wrong_size = [
        probe["n"] for probe in probes
        if probe["width"] != width or probe["height"] != height
    ]
    checks["geometry"] = (
        _fail(f"wrong canvas {width}x{height}: {wrong_size}")
        if wrong_size
        else _pass(f"all shots are {width}x{height}")
    )

    # 3. Duration matches the beat window.
    wrong_length = []
    for shot, probe in zip(shots, probes):
        expected = shot["t_out"] - shot["t_in"]
        if abs(probe["duration_seconds"] - expected) > DURATION_TOLERANCE_SECONDS:
            wrong_length.append(
                f"{shot['n']}: {probe['duration_seconds']}s vs {expected}s"
            )
    checks["duration"] = (
        _fail(f"duration outside ±{DURATION_TOLERANCE_SECONDS}s: {wrong_length}")
        if wrong_length
        else _pass("every shot matches its beat window")
    )

    # 4. Audio, when the render is expected to carry it.
    if require_audio:
        silent = [probe["n"] for probe in probes if not probe["has_audio"]]
        checks["audio"] = (
            _fail(f"no audio track: {silent}") if silent
            else _pass("every shot carries audio")
        )
    else:
        checks["audio"] = _skipped("audio not required for this render")

    # 5. Captions are byte-exact against the source pack.
    beats = [
        {"n": shot["n"], "caption_lines": shot.get("caption_lines") or []}
        for shot in shots
    ]
    ungrounded = check_caption_grounding(beats, source_text)
    checks["captions"] = (
        _fail(f"captions not grounded in the source: {ungrounded}")
        if ungrounded
        else _pass("every caption appears verbatim in the pack")
    )

    # 6. Contact sheet for human review.
    try:
        sheet = build_contact_sheet(frames, directory / "contact_sheet.jpg")
        checks["contact_sheet"] = _pass(str(sheet))
    except QAGateError as exc:
        checks["contact_sheet"] = _fail(str(exc))

    passed = all(
        check.get("status") == "PASS"
        for check in checks.values()
        if isinstance(check, dict)
    )
    return _report(checks, directory, frames, passed=passed)


def _pass(reason: str) -> dict[str, str]:
    return {"status": "PASS", "reason": reason}


def _fail(reason: str) -> dict[str, str]:
    return {"status": "FAIL", "reason": reason}


def _skipped(reason: str) -> dict[str, str]:
    return {"status": "SKIPPED", "reason": reason}


def _report(
    checks: dict[str, Any], directory: Path, frames: list[Path], *, passed: bool
) -> dict[str, Any]:
    return {
        "passed": passed,
        "checks": checks,
        "frames": [str(frame) for frame in frames],
        "report_dir": str(directory),
    }
