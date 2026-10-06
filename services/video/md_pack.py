"""Parse a scenario pack markdown into beats, deterministically.

The pack is the source of truth for a composed video: it carries the exact
on-screen transcript, the timestamps, and how each beat should be sourced. No
LLM is involved and no caption is invented -- every caption line must appear
in the source markdown byte for byte.

Pack format (one or more concepts, each a `## N.` section):

    ## 1. Concept title

    Buyer: ...
    Target duration: 0:49

    **0:00–0:06 — label**
    CAPTION LINE ONE
    CAPTION LINE TWO

    **0:06–0:14 — label**
    ...

    **Beat 1 — label**
    - Visible: ...
    - Preferred visual type: ...
    - Search: ...
    - Portrait crop: ...
    - Motion: ...
    - Connection: ...
    - Fallback generated-image prompt: ...

    **Beat 2 — label**
    ...

A concept fails to parse when the transcript beat count differs from the
sourcing beat count, when timestamps overlap or leave a gap, or when the last
timestamp does not match the stated target duration.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# A timed transcript header: **0:00–0:06 — label** (en dash, em dash).
TIMED_HEADER_RE = re.compile(
    r"^\*\*(?P<t_in>\d+:\d{2}(?::\d{2})?)\s*[-\u2013\u2014]\s*"
    r"(?P<t_out>\d+:\d{2}(?::\d{2})?)\s*[-\u2013\u2014]\s*(?P<label>.+?)\*\*\s*$"
)
# A sourcing header: **Beat 1 — label**
BEAT_HEADER_RE = re.compile(
    r"^\*\*Beat\s+(?P<n>\d+)\s*[-\u2013\u2014]\s*(?P<label>.+?)\*\*\s*$"
)
FIELD_RE = re.compile(r"^[-*]\s*(?P<key>[^:]+?)\s*:\s*(?P<value>.*)$")
CONCEPT_RE = re.compile(r"^##\s+(?P<n>\d+)\.?\s*(?P<title>.+?)\s*$")
DURATION_RE = re.compile(r"^(?P<mins>\d+):(?P<secs>\d{2})$")

# A beat is GPU-eligible only when its type asks for generated imagery.
GENERATED_TYPE_CUES = (
    "generated", "illustrative", "illustration", "ai generated",
    "ai-generated", "synthetic", "mood", "atmospheric", "b-roll", "b roll",
    "opener", "outro", "intro",
)
NOT_NEEDED = {"not needed", "n/a", "none", "no", "-", ""}


class PackError(ValueError):
    """Raised when a pack cannot be parsed or fails structural validation."""


TIMESTAMP_RE = re.compile(r"^(?:(\d+):)?([0-5]?\d):([0-5]\d)$")


def parse_timestamp(value: str) -> float:
    """`0:06` or `1:02:03` -> seconds. Raises PackError on bad input."""
    match = TIMESTAMP_RE.match(value.strip())
    if not match:
        raise PackError(f"bad timestamp {value!r}")
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2))
    seconds = int(match.group(3))
    return hours * 3600 + minutes * 60 + seconds


def format_timestamp(seconds: float) -> str:
    """Seconds -> `M:SS`, the pack's own timestamp spelling."""
    total = int(round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


@dataclass
class Beat:
    """One timed beat: the caption to show and how to source the picture."""

    n: int
    t_in: float
    t_out: float
    caption_lines: list[str] = field(default_factory=list)
    visible: str = ""
    preferred_type: str = ""
    search: str = ""
    crop_focus: str = ""
    motion: list[str] = field(default_factory=list)
    connection: str = ""
    fallback_prompt: str = ""
    generate: bool = False

    @property
    def duration(self) -> float:
        return self.t_out - self.t_in

    def as_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "t_in": self.t_in,
            "t_out": self.t_out,
            "duration": round(self.duration, 3),
            "caption_lines": list(self.caption_lines),
            "source": {
                "type": self.preferred_type or "stock",
                "search": self.search,
                "file": "",
            },
            "crop": {"focus": self.crop_focus or "centre"},
            "motion": list(self.motion),
            "generate": self.generate,
            "fallback_prompt": self.fallback_prompt,
        }


@dataclass
class Concept:
    """One `## N.` section of a pack: a title, a buyer and its beats."""

    n: int
    title: str
    buyer: str = ""
    target_duration: float | None = None
    beats: list[Beat] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "title": self.title,
            "buyer": self.buyer,
            "target_duration": self.target_duration,
            "beats": [beat.as_dict() for beat in self.beats],
        }


def _is_generated_type(preferred: str) -> bool:
    haystack = preferred.lower()
    return any(cue in haystack for cue in GENERATED_TYPE_CUES)


def _decide_generate(preferred: str, fallback: str) -> bool:
    """GPU eligibility: the type must ask for generated imagery AND a usable
    fallback prompt must exist. "Not needed" means the beat is deterministic.
    """
    if not _is_generated_type(preferred):
        return False
    return fallback.strip().lower() not in NOT_NEEDED


def _parse_concept(block: str, n: int, title: str) -> Concept:
    concept = Concept(n=n, title=title)
    lines = block.splitlines()

    timed: list[tuple[float, float, list[str]]] = []
    sourced: dict[int, dict[str, str]] = {}
    current_timed: list[float] | None = None
    current_caption: list[str] | None = None
    current_beat: int | None = None
    current_fields: dict[str, str] | None = None

    def flush_timed() -> None:
        if current_timed is not None and current_caption is not None:
            timed.append((current_timed[0], current_timed[1], list(current_caption)))

    def flush_beat() -> None:
        if current_beat is not None and current_fields is not None:
            sourced[current_beat] = dict(current_fields)

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            continue

        header = TIMED_HEADER_RE.match(stripped)
        if header:
            flush_timed()
            current_timed = (
                parse_timestamp(header.group("t_in")),
                parse_timestamp(header.group("t_out")),
            )
            current_caption = []
            current_beat = None
            current_fields = None
            continue

        beat_header = BEAT_HEADER_RE.match(stripped)
        if beat_header:
            # Leaving the transcript section: the final timed beat has to be
            # flushed here, or it is dropped when sourcing begins.
            flush_timed()
            flush_beat()
            current_beat = int(beat_header.group("n"))
            current_fields = {}
            current_timed = None
            current_caption = None
            continue

        field = FIELD_RE.match(stripped)
        if field and current_fields is not None:
            key = field.group("key").strip().lower()
            current_fields[key] = field.group("value").strip()
            continue

        if current_caption is not None:
            current_caption.append(stripped)
            continue

        # Concept-level metadata, before any beat header.
        lowered = stripped.lower()
        if lowered.startswith("buyer:"):
            concept.buyer = stripped.split(":", 1)[1].strip()
        elif lowered.startswith("target duration:"):
            concept.target_duration = parse_timestamp(
                stripped.split(":", 1)[1].strip()
            )

    flush_timed()
    flush_beat()

    if not timed:
        raise PackError(f"concept {n} ({title!r}) has no timed transcript beats")
    if len(timed) != len(sourced):
        raise PackError(
            f"concept {n} ({title!r}): {len(timed)} transcript beats but "
            f"{len(sourced)} sourcing beats -- they must match one to one"
        )

    for index, ((t_in, t_out, captions), beat_n) in enumerate(
        zip(timed, sorted(sourced)), start=1
    ):
        if beat_n != index:
            raise PackError(
                f"concept {n} ({title!r}): sourcing beat {beat_n} is out of "
                f"order (expected {index})"
            )
        fields = sourced[beat_n]
        preferred = fields.get("preferred visual type", "")
        fallback = fields.get("fallback generated-image prompt", "")
        concept.beats.append(
            Beat(
                n=index,
                t_in=t_in,
                t_out=t_out,
                caption_lines=captions,
                visible=fields.get("visible", ""),
                preferred_type=preferred,
                search=fields.get("search", ""),
                crop_focus=fields.get("portrait crop", ""),
                motion=[
                    part.strip()
                    for part in fields.get("motion", "").split(",")
                    if part.strip()
                ],
                connection=fields.get("connection", ""),
                fallback_prompt=fallback,
                generate=_decide_generate(preferred, fallback),
            )
        )

    _validate_timestamps(concept)
    return concept


def _validate_timestamps(concept: Concept) -> None:
    """Timestamps must be ordered, contiguous and match the target duration."""
    beats = concept.beats
    for previous, current in zip(beats, beats[1:]):
        if current.t_in < previous.t_out:
            raise PackError(
                f"concept {concept.n} ({concept.title!r}): beat {current.n} "
                f"starts at {format_timestamp(current.t_in)} before beat "
                f"{previous.n} ends at {format_timestamp(previous.t_out)}"
            )
        if current.t_in > previous.t_out:
            raise PackError(
                f"concept {concept.n} ({concept.title!r}): gap between beat "
                f"{previous.n} (ends {format_timestamp(previous.t_out)}) and "
                f"beat {current.n} (starts {format_timestamp(current.t_in)})"
            )
    if concept.target_duration is None:
        raise PackError(
            f"concept {concept.n} ({concept.title!r}): no target duration"
        )
    actual = beats[-1].t_out
    if abs(actual - concept.target_duration) > 0.001:
        raise PackError(
            f"concept {concept.n} ({concept.title!r}): last timestamp "
            f"{format_timestamp(actual)} does not match the stated target "
            f"duration {format_timestamp(concept.target_duration)}"
        )


def parse_pack(text: str) -> list[Concept]:
    """Parse pack markdown into concepts. Raises PackError on any defect."""
    if not text or not text.strip():
        raise PackError("pack is empty")

    blocks: list[tuple[int, str, str]] = []
    current_n: int | None = None
    current_title = ""
    buffer: list[str] = []

    for line in text.splitlines():
        match = CONCEPT_RE.match(line.strip())
        if match:
            if current_n is not None:
                blocks.append((current_n, current_title, "\n".join(buffer)))
            current_n = int(match.group("n"))
            current_title = match.group("title").strip()
            buffer = []
        elif current_n is not None:
            buffer.append(line)
    if current_n is not None:
        blocks.append((current_n, current_title, "\n".join(buffer)))

    if not blocks:
        raise PackError("pack has no '## N.' concept sections")

    concepts = [
        _parse_concept(block, n, title) for n, title, block in blocks
    ]
    numbers = [concept.n for concept in concepts]
    if numbers != list(range(1, len(concepts) + 1)):
        raise PackError(f"concept numbers must be 1..n in order, got {numbers}")
    return concepts


def beats_json(concepts: list[Concept]) -> dict[str, Any]:
    """The single source of truth the compose stage consumes."""
    return {
        "concepts": [concept.as_dict() for concept in concepts],
        "total_duration": max(
            (beat.t_out for concept in concepts for beat in concept.beats),
            default=0.0,
        ),
        "gpu_beats": sum(
            1 for concept in concepts for beat in concept.beats if beat.generate
        ),
    }


def load_pack(path: str | Path) -> list[Concept]:
    """Read and parse a pack file."""
    return parse_pack(Path(path).read_text(encoding="utf-8"))
