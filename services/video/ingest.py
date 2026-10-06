"""Ingest a scenario pack and its media assets for a composed video.

The pack is the source of truth and arrives through the UI when the operator
starts a render, so this module is the boundary between an uploaded file and
the deterministic pipeline: it stores the bytes unchanged, validates them, and
registers them against a project.

Nothing here generates anything. A pack that fails to parse is rejected before
it can reach the compose stage, and an unreadable media file is rejected rather
than silently producing a broken video.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path
from typing import Any

from services.video.md_pack import PackError, parse_pack

# Media the compose stage can actually use, mapped to the asset `type` the
# router assigns. Anything else is rejected rather than guessed at.
MEDIA_SUFFIXES = {
    ".mp4": "founder_footage",
    ".mov": "founder_footage",
    ".webm": "founder_footage",
    ".png": "ui_capture",
    ".jpg": "ui_capture",
    ".jpeg": "ui_capture",
    ".svg": "logo",
}
PACK_SUFFIXES = {".md", ".markdown", ".txt"}
MAX_MEDIA_BYTES = 2_000_000_000
MAX_PACK_BYTES = 2_000_000


class IngestError(RuntimeError):
    """Raised when an upload cannot be accepted."""


def workspace_root() -> Path:
    """Root that all uploaded media must stay inside."""
    return (Path(__file__).resolve().parents[2] / "projects").resolve()


def ingest_dir(project_id: str) -> Path:
    """Per-project ingest directory, created on demand.

    The id is used as a single path component, so anything that could escape
    the workspace is rejected before a directory is created.
    """
    if not project_id or "/" in project_id or "\\" in project_id:
        raise IngestError(f"unsafe project id: {project_id!r}")
    safe = Path(project_id).name
    if safe in {"", ".", ".."}:
        raise IngestError(f"unsafe project id: {project_id!r}")
    target = workspace_root() / safe / "ingest"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def probe_media(path: Path) -> dict[str, Any]:
    """Read duration, resolution and codec from a media file.

    Raises IngestError when the file is not decodable, so a truncated upload
    cannot reach the compose stage.
    """
    if shutil.which("ffprobe") is None:
        raise IngestError("ffprobe is required to validate uploads")
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries",
            "format=duration:stream=codec_type,codec_name,width,height",
            "-of", "json", str(path),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode:
        detail = (result.stderr or "").strip()[-300:]
        raise IngestError(f"unreadable media file: {detail or 'ffprobe failed'}")
    try:
        import json

        payload = json.loads(result.stdout or "{}")
    except ValueError as exc:
        raise IngestError("ffprobe returned non-JSON") from exc

    video_streams = [
        stream for stream in (payload.get("streams") or [])
        if stream.get("codec_type") == "video"
    ]
    if not video_streams:
        raise IngestError("media file has no video stream")
    stream = video_streams[0]
    if not stream.get("width") or not stream.get("height"):
        raise IngestError("media file has no decodable dimensions")
    try:
        duration = float((payload.get("format") or {}).get("duration") or 0.0)
    except (TypeError, ValueError) as exc:
        raise IngestError("media file has an unreadable duration") from exc
    if duration <= 0:
        raise IngestError("media file has a non-positive duration")
    return {
        "duration_seconds": round(duration, 3),
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "codec": stream.get("codec_name"),
    }


def store_pack(project_id: str, filename: str, data: bytes) -> dict[str, Any]:
    """Store an uploaded pack and parse it. Returns the parsed concepts."""
    if len(data) > MAX_PACK_BYTES:
        raise IngestError(
            f"pack is {len(data)} bytes, over the {MAX_PACK_BYTES} limit"
        )
    suffix = Path(filename or "").suffix.lower()
    if suffix not in PACK_SUFFIXES:
        raise IngestError(
            f"a pack must be markdown ({', '.join(sorted(PACK_SUFFIXES))}), "
            f"got {suffix or 'no extension'}"
        )
    target = ingest_dir(project_id) / f"pack{suffix}"
    target.write_bytes(data)
    try:
        concepts = parse_pack(data.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise IngestError("pack must be UTF-8 text") from exc
    except PackError as exc:
        raise IngestError(f"pack rejected: {exc}") from exc
    return {
        "path": str(target),
        "size_bytes": len(data),
        "sha256": _sha256(target),
        "concepts": [concept.as_dict() for concept in concepts],
        "total_duration": max(
            (beat.t_out for concept in concepts for beat in concept.beats),
            default=0.0,
        ),
        "gpu_beats": sum(
            1 for concept in concepts for beat in concept.beats if beat.generate
        ),
    }


def store_media(
    project_id: str,
    filename: str,
    data: bytes,
    tag: str | None = None,
) -> dict[str, Any]:
    """Store an uploaded media file, validate it, and describe it for the UI.

    The original bytes are written unchanged; the returned record carries the
    asset `type` the router will assign, derived from the suffix unless the
    caller tags it explicitly.
    """
    if len(data) > MAX_MEDIA_BYTES:
        raise IngestError(
            f"media is {len(data)} bytes, over the {MAX_MEDIA_BYTES} limit"
        )
    suffix = Path(filename or "").suffix.lower()
    if suffix not in MEDIA_SUFFIXES:
        raise IngestError(
            f"unsupported media type {suffix or '(none)'}; allowed: "
            f"{', '.join(sorted(MEDIA_SUFFIXES))}"
        )
    asset_type = (tag or MEDIA_SUFFIXES[suffix]).strip().lower()
    if not asset_type:
        raise IngestError("asset tag must not be empty")

    target = ingest_dir(project_id) / f"{_sha256_bytes(data)}{suffix}"
    target.write_bytes(data)
    try:
        probe = probe_media(target)
    except IngestError:
        target.unlink(missing_ok=True)
        raise
    return {
        "path": str(target),
        "type": asset_type,
        "size_bytes": len(data),
        "sha256": _sha256(target),
        **probe,
    }


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]
