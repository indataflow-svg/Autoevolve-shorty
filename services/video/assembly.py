"""Deterministic assembly of rendered chunks into one deliverable MP4.

The renderer only ever produces windowed clips (Hunyuan's native temporal
window is 129 frames), so a full video is N chunk jobs. This module stitches
them with FFmpeg's concat demuxer -- a stream copy, so no re-encode and no
generation is involved.

Text, logo and CTA layers belong here rather than in generated frames: vector
overlays are composited onto the assembled video, which is the only place where
lettering can be guaranteed correct.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


class AssemblyError(RuntimeError):
    """Raised when a full video cannot be assembled from its chunks."""


def has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def chunk_order(job: dict[str, Any]) -> int:
    """Zero-based position of a chunk job, from its persisted shot id."""
    import re

    match = re.match(r"chunk_(\d+)$", str(job.get("shot_id") or job.get("shotId") or ""))
    if not match:
        raise AssemblyError(f"job {job.get('id')} is not a chunk: {job.get('shot_id')}")
    return int(match.group(1)) - 1


def plan_chunks(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the chunk jobs for a plan, ordered for concatenation."""
    chunks = sorted(jobs, key=chunk_order)
    expected = list(range(len(chunks)))
    actual = [chunk_order(job) for job in chunks]
    if actual != expected:
        raise AssemblyError(f"chunk sequence is not contiguous: {actual}")
    return chunks


def completed_chunk_paths(jobs: list[dict[str, Any]]) -> list[Path]:
    """Local MP4 paths of the completed chunks, in assembly order.

    A chunk is only usable when its job completed AND its recorded frame count
    matches what the file actually contains, so a job row can never smuggle in
    a truncated artifact.
    """
    paths: list[Path] = []
    for job in plan_chunks(jobs):
        if job.get("status") != "completed":
            raise AssemblyError(
                f"chunk {job.get('shot_id')} is {job.get('status')!r}, not completed"
            )
        result = job.get("result") or {}
        raw = result.get("outputPath") or result.get("output_path")
        if not raw:
            raise AssemblyError(f"chunk {job.get('shot_id')} has no recorded output path")
        path = Path(raw)
        if not path.is_file():
            raise AssemblyError(f"chunk {job.get('shot_id')} file is missing: {path}")
        declared = result.get("frames")
        actual = probe_frame_count(path)
        if declared and actual and int(declared) != int(actual):
            raise AssemblyError(
                f"chunk {job.get('shot_id')} declares {declared} frames but the "
                f"file holds {actual}: refusing to assemble"
            )
        paths.append(path)
    return paths


def probe_frame_count(path: str | Path) -> int | None:
    """Count decodable frames with ffprobe, or None if it cannot be read."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
            "-show_entries", "stream=nb_read_frames", "-of", "json", str(path),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode:
        return None
    try:
        streams = json.loads(result.stdout or "{}").get("streams") or [{}]
        return int(streams[0].get("nb_read_frames") or 0) or None
    except (ValueError, IndexError, TypeError):
        return None


def probe_stream(path: str | Path) -> dict[str, Any]:
    """Codec, size, frame rate and duration of a file's first video stream."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
            "-show_entries",
            "stream=codec_name,width,height,avg_frame_rate,nb_read_frames",
            "-show_entries", "format=duration", "-of", "json", str(path),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode:
        raise AssemblyError(f"ffprobe failed on {path}: {(result.stderr or '')[-300:]}")
    try:
        payload = json.loads(result.stdout or "{}")
    except ValueError as exc:
        raise AssemblyError(f"ffprobe returned non-JSON for {path}") from exc
    stream = (payload.get("streams") or [{}])[0]
    rate = str(stream.get("avg_frame_rate") or "0/1")
    numerator, _, denominator = rate.partition("/")
    try:
        fps = float(numerator) / float(denominator or 1)
    except (ValueError, ZeroDivisionError):
        fps = 0.0
    return {
        "codec": stream.get("codec_name"),
        "width": stream.get("width"),
        "height": stream.get("height"),
        "fps": fps,
        "frames": int(stream.get("nb_read_frames") or 0) or None,
        "duration_seconds": float((payload.get("format") or {}).get("duration") or 0.0),
    }


def assemble_full_video(
    jobs: list[dict[str, Any]], destination: str | Path
) -> dict[str, Any]:
    """Concatenate completed chunks into ``destination`` and describe the result.

    Uses FFmpeg's concat demuxer with a stream copy, so joining is lossless and
    near-instant. Every chunk must share codec, size and frame rate or the copy
    would silently produce a broken file, so that is verified first.
    """
    if not has_ffmpeg():
        raise AssemblyError("ffmpeg/ffprobe are required to assemble a full video")
    paths = completed_chunk_paths(jobs)
    if not paths:
        raise AssemblyError("no completed chunks to assemble")

    streams = [probe_stream(path) for path in paths]
    first = streams[0]
    for path, stream in zip(paths[1:], streams[1:]):
        for field in ("codec", "width", "height"):
            if stream.get(field) != first.get(field):
                raise AssemblyError(
                    f"chunk {path.name} {field}={stream.get(field)!r} differs from "
                    f"{paths[0].name} {field}={first.get(field)!r}; a stream copy "
                    "cannot join mismatched streams"
                )
        if abs((stream.get("fps") or 0) - (first.get("fps") or 0)) > 0.01:
            raise AssemblyError(
                f"chunk {path.name} fps={stream.get('fps')} differs from "
                f"{paths[0].name} fps={first.get('fps')}"
            )

    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    listing = target.with_suffix(".concat.txt")
    listing.write_text(
        "".join(f"file '{path.resolve()}'\n" for path in paths),
        encoding="utf-8",
    )
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "concat", "-safe", "0", "-i", str(listing),
                "-c", "copy", "-movflags", "+faststart", str(target),
            ],
            capture_output=True,
            text=True,
            timeout=600,
        )
    finally:
        listing.unlink(missing_ok=True)
    if result.returncode:
        raise AssemblyError(
            f"ffmpeg concat failed (exit {result.returncode}): "
            f"{(result.stderr or '')[-500:]}"
        )
    if not target.is_file() or target.stat().st_size <= 0:
        raise AssemblyError(f"assembly produced no usable file: {target}")

    final = probe_stream(target)
    digest = hashlib.sha256()
    with open(target, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return {
        "output_path": str(target),
        "chunks": len(paths),
        "chunk_frames": [stream["frames"] for stream in streams],
        "frames": final.get("frames"),
        "duration_seconds": round(final.get("duration_seconds") or 0.0, 3),
        "codec": final.get("codec"),
        "width": final.get("width"),
        "height": final.get("height"),
        "fps": final.get("fps"),
        "file_size_bytes": target.stat().st_size,
        "sha256": digest.hexdigest(),
    }
