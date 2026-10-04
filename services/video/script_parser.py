"""Deterministic script parsing: timed beats plus the visual association map."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

TIMESTAMP_RE = re.compile(r"^(?:(\d+):)?([0-5]?\d):([0-5]\d)$")
BEAT_HEADER_RE = re.compile(r"^(?:#{1,3}\s*)?(\d+:[\d:]+\s*[-\u2013\u2014]\s*\d+:[\d:]+)\s*$")
VISUAL_FIELD_RE = re.compile(r"^(visual|type|search|motion|connection|source)\s*:\s*(.+)$", re.IGNORECASE)
META_FIELD_RE = re.compile(
    r"^(buyer|duration|narrative|cta|product\s*boundary|target\s*buyer|objective|message|platform|"
    r"visual\s*style|style|emotion|emotional\s*direction|audio)\s*:\s*(.+)$", re.IGNORECASE
)


def parse_timestamp(value: str) -> float:
    match = TIMESTAMP_RE.match(value.strip())
    if not match:
        raise ValueError(f"invalid timestamp: {value!r} (expected M:SS or H:MM:SS)")
    hours, minutes, seconds = match.groups()
    return int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds)


def parse_beat_range(value: str) -> tuple[float, float]:
    parts = re.split(r"\s*[-\u2013\u2014]\s*", value.strip())
    if len(parts) != 2:
        raise ValueError(f"invalid beat range: {value!r}")
    return parse_timestamp(parts[0]), parse_timestamp(parts[1])


def format_timestamp(seconds: float) -> str:
    total = int(round(seconds))
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def parse_script(text: str, source_name: str = "script") -> dict[str, Any]:
    """Parse a prepared script into title, metadata and timed visual beats.

    Beat headers are ``0:00-0:06`` (hyphen, en dash and em dash all accepted,
    with or without ``##``). Body lines starting with ``Visual:`` / ``Type:`` /
    ``Search:`` / ``Motion:`` / ``Connection:`` / ``Source:`` form the
    transcript-to-visual association; every other non-empty line is spoken
    text and is preserved verbatim. ``Buyer:`` / ``Narrative:`` / ``CTA:`` /
    ``Product boundary:`` lines before the first beat become spec metadata.
    """
    title: str | None = None
    meta: dict[str, str] = {}
    beats: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    text_lines: list[str] = []

    def flush() -> None:
        if not current:
            return
        body = "\n".join(text_lines).strip()
        current["text"] = body
        beats.append(current)

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("# ") and title is None and not beats:
            title = line[2:].strip()
            continue
        header = BEAT_HEADER_RE.match(line)
        if header:
            flush()
            text_lines = []
            start, end = parse_beat_range(header.group(1))
            current = {
                "id": f"beat_{len(beats) + 1:02d}",
                "startSeconds": start,
                "endSeconds": end,
                "text": "",
                "visual": {},
            }
            continue
        visual = VISUAL_FIELD_RE.match(line)
        if visual and current is not None:
            current["visual"][visual.group(1).lower()] = visual.group(2).strip()
            continue
        meta_match = META_FIELD_RE.match(line)
        if meta_match and current is None:
            meta[meta_match.group(1).lower().replace(" ", "_")] = meta_match.group(2).strip()
            continue
        if current is None:
            # Prose before the first beat header: treat as narrative context.
            meta.setdefault("preamble", "")
            meta["preamble"] = (meta["preamble"] + "\n" + line).strip()
            continue
        text_lines.append(raw_line.rstrip())

    flush()
    if not beats:
        raise ValueError(f"{source_name}: no timed beats found (expected headers like '0:00-0:06')")
    return {
        "title": title or meta.get("title") or Path(source_name).stem.replace("_", " ").title(),
        "meta": meta,
        "beats": beats,
    }
