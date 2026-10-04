"""VideoSpec -> ShotPlan -> RenderJob pipeline (control plane side).

The pipeline is deterministic by default: parsing, validation, visual-type
routing, frame math, output paths and seeds never need a model. When a model
router key is configured (``OMNIROUTE_API_KEY``), the AI layer refines visual
prompts and continuity notes; every AI call has a deterministic fallback, the
same pattern as ``services/asset_scene_planner.py``.

AI / deterministic split (prompt.md section 5):

- SCRIPT -> VIDEOSPEC: deterministic parser only. Transcript wording is a
  factual source and must never be rewritten by a model.
- SHOT PLANNER: deterministic beat -> shot boundaries and visual-type routing
  (section 4 rules); the AI only refines purposes, never timing.
- VISUAL PROMPT GENERATOR: AI when configured, template fallback otherwise.
- CONTINUITY CHECK: deterministic chain builder plus a deterministic validator;
  the AI adds continuity notes when configured.

Nothing here renders anything. Render jobs are queue records consumed by the
external MI300X worker (see docs/video-pipeline.md).
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from core.models import is_model_configured

KNOWLEDGE_DIR = (
    Path(__file__).parent.parent / "engines" / "g1" / "knowledge" / "_drafts" / "indataflow"
)

HUNYUAN_DEFAULT_PROFILE: dict[str, Any] = {
    "resolution": "480p",
    "fps": 24,
    "steps": 20,
    "dtype": "bf16",
    "seed": 42,
    "rewrite": False,
    "offloading": False,
    "sr": False,
    "cfg_distilled": False,
    "enable_step_distill": False,
}

FORMAT_SIZES = {
    "4:5": (1080, 1350),
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
    "1:1": (1080, 1080),
}

DEFAULT_NEGATIVE_PROMPT = (
    "blurry, low quality, distorted, deformed, malformed hands, extra fingers, "
    "duplicated objects, flickering, unstable geometry, temporal inconsistency, "
    "camera jitter, text artifacts, legible text, logos, user interfaces, "
    "watermark, logo artifacts, cartoon, anime"
)

VISUAL_TYPES = (
    "hunyuan",
    "stock",
    "product_capture",
    "motion_graphics",
    "source_capture",
    "brand_end_frame",
    "mixed",
)

RENDERER_FOR_TYPE = {
    "hunyuan": "hunyuan",
    "motion_graphics": "motion_graphics",
    "stock": "asset",
    "product_capture": "asset",
    "source_capture": "asset",
    "brand_end_frame": "ffmpeg",
    "mixed": "ffmpeg",  # refined per-shot by _primary_renderer
}

# Deterministic visual-type routing (prompt.md section 4). Each family lists
# lowercase cue phrases matched against the beat's visual notes + spoken text.
ROUTE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "brand_end_frame": (
        "end frame", "end card", "closing card", "book a walkthrough", "cta card",
    ),
    "motion_graphics": (
        "text overlay", "caption", "diagram", "timeline", "route line",
        "route redraw", "map route", "data relationship", "chart", "transition",
        "logo", "overlay",
    ),
    "product_capture": (
        "indataflow ui", "product screen", "screenshot",
        "upload", "validation state", "client dashboard", "operations dashboard",
        "app screen", "product ui", "control layer",
    ),
    "source_capture": (
        "source", "iru", "report", "authority", "official", "statistics",
        "according to", "cites", "reference",
    ),
    "hunyuan": (
        "cinematic", "camera movement", "camera push", "tracking shot",
        "sunrise", "aerial", "atmospheric", "slow push", "dolly",
    ),
    "stock": (
        "truck", "ship", "port", "warehouse", "document", "people", "driver",
        "customs", "cargo", "container", "footage", "freight", "border",
        "crane", "highway", "corridor",
    ),
}

# Renderer precedence when a shot mixes production families: generated footage
# first, then the authored assembly (brand end cards via ffmpeg, graphics via
# the motion renderer), with acquisition (asset) as the fallback owner.
MIXED_RENDERER_PRECEDENCE = ("hunyuan", "ffmpeg", "motion_graphics", "asset")

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


def load_indataflow_context() -> dict[str, Any]:
    """Load brand/product/CTA guardrails from the existing G1 knowledge files."""
    context: dict[str, Any] = {}
    for name in (
        "brand_profile",
        "product_claims",
        "prohibited_claims",
        "cta_registry",
        "narrative_registry",
        "icp_registry",
    ):
        path = KNOWLEDGE_DIR / f"{name}.json"
        try:
            context[name] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            context[name] = {}
    return context


def _forbidden_phrases(context: dict[str, Any]) -> list[str]:
    phrases: list[str] = []
    prohibited = context.get("prohibited_claims") or {}
    if isinstance(prohibited, dict):
        for key in (
            "forbidden",
            "forbidden_claims",
            "prohibited",
            "never_claim",
            "case_insensitive_terms",
            "internal_topics",
        ):
            values = prohibited.get(key)
            if isinstance(values, list):
                phrases.extend(str(item) for item in values)
    cta = context.get("cta_registry") or {}
    if isinstance(cta, dict):
        for key in ("forbidden_offers", "unconfirmed_trial_claims"):
            values = cta.get(key)
            if isinstance(values, list):
                phrases.extend(str(item) for item in values)
    brand = context.get("brand_profile") or {}
    if isinstance(brand, dict):
        avoid = brand.get("avoid_voice")
        if isinstance(avoid, list):
            phrases.extend(str(item) for item in avoid)
    seen: set[str] = set()
    unique = [item for item in phrases if item and not (item in seen or seen.add(item))]
    return unique


def _forbidden_patterns(context: dict[str, Any]) -> list["re.Pattern[str]"]:
    patterns: list["re.Pattern[str]"] = []
    prohibited = context.get("prohibited_claims") or {}
    if isinstance(prohibited, dict):
        values = prohibited.get("patterns")
        if isinstance(values, list):
            for value in values:
                try:
                    patterns.append(re.compile(str(value), re.IGNORECASE))
                except re.error:
                    continue
    return patterns


def build_spec(
    parsed: dict[str, Any],
    *,
    project_id: str,
    campaign_id: str | None = None,
    aspect_ratio: str = "9:16",
    fps: int = 24,
    source_path: str | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an (unsaved) VideoSpec dict from parsed script beats."""
    if aspect_ratio not in FORMAT_SIZES:
        raise ValueError(f"unsupported aspect ratio: {aspect_ratio!r}")
    context = context if context is not None else load_indataflow_context()
    brand = context.get("brand_profile") or {}
    cta_registry = context.get("cta_registry") or {}
    meta = parsed.get("meta") or {}
    width, height = FORMAT_SIZES[aspect_ratio]
    beats = parsed["beats"]
    duration = max(beat["endSeconds"] for beat in beats)
    default_cta = "Book a walkthrough."
    if isinstance(cta_registry, dict):
        default_cta = str(cta_registry.get("walkthrough", {}).get("copy", default_cta))
    return {
        "projectId": project_id,
        "campaignId": campaign_id,
        "title": parsed["title"],
        "brand": {
            "name": brand.get("brand", "InDataFlow") if isinstance(brand, dict) else "InDataFlow",
            "visualStyle": "restrained blue and indigo, premium commercial cinematography",
            "colors": ["#1B2A6B", "#2E5AAC", "#E8EDF7"],
        },
        "format": {
            "aspectRatio": aspect_ratio,
            "width": width,
            "height": height,
            "durationSeconds": duration,
            "fps": fps,
        },
        "audience": {
            "buyer": meta.get("buyer") or meta.get("target_buyer"),
            "segment": None,
        },
        "narrative": meta.get("narrative") or meta.get("preamble"),
        "transcript": [
            {
                "id": beat["id"],
                "startSeconds": beat["startSeconds"],
                "endSeconds": beat["endSeconds"],
                "text": beat["text"],
            }
            for beat in beats
        ],
        "visualRules": {
            "preferredStyle": "authentic logistics footage first; cinematic generation for camera movement",
            "footagePriority": "stock, source_capture, hunyuan",
            "generatedGraphicsAllowed": True,
            "fakeDashboardsAllowed": False,
            "fakeDocumentsAllowed": False,
            "watermarkAllowed": False,
        },
        "brandConstraints": {
            "colors": ["#1B2A6B", "#2E5AAC", "#E8EDF7"],
            "typography": "condensed uppercase headlines",
            "logoRequired": True,
        },
        "productBoundary": meta.get("product_boundary")
        or "Only approved product claims; never show unreleased UI, fake dashboards, or fabricated statistics.",
        "cta": meta.get("cta") or default_cta,
        "extra": {
            "objective": meta.get("objective"),
            "message": meta.get("message"),
            "platform": meta.get("platform"),
            "visual_style": meta.get("visual_style") or meta.get("style"),
            "emotional_direction": meta.get("emotional_direction") or meta.get("emotion"),
            "audio": meta.get("audio"),
        },
        "sources": [
            {"title": beat["visual"].get("source", ""), "url": ""}
            for beat in beats
            if beat.get("visual", {}).get("source")
        ],
        "assets": [
            {
                "id": f"asset_{beat['id']}",
                "type": "source_reference",
                "path": beat["visual"].get("source", ""),
                "purpose": f"source for {beat['id']}",
                "identity_priority": 5,
                "preserve": ["source identity", "attribution"],
                "allowed_changes": ["crop", "caption overlay"],
            }
            for beat in beats
            if beat.get("visual", {}).get("source")
        ],
        "sourceScriptId": None,
        "source_path": source_path,
        "_beats_visual": {beat["id"]: beat.get("visual", {}) for beat in beats},
        "status": "draft",
    }


def validate_spec(spec: dict[str, Any]) -> None:
    """Raise ValueError unless the spec satisfies prompt.md section 12."""
    errors: list[str] = []
    beats = spec.get("transcript") or []
    if not beats:
        errors.append("spec has no transcript beats")
        return _raise(errors)
    previous_end: float | None = None
    for index, beat in enumerate(beats):
        start, end = beat.get("startSeconds"), beat.get("endSeconds")
        if start is None or end is None:
            errors.append(f"beat {beat.get('id', index)} is missing timestamps")
            continue
        if end <= start:
            errors.append(f"beat {beat.get('id', index)} has a non-positive duration")
        if index == 0 and start != 0:
            errors.append(f"first beat must start at 0, starts at {start}")
        if previous_end is not None and start != previous_end:
            errors.append(
                f"beat {beat.get('id', index)} starts at {start} but the previous beat ends at {previous_end}"
            )
        if not str(beat.get("text") or "").strip():
            errors.append(f"beat {beat.get('id', index)} has no spoken text")
        previous_end = end
    total = spec.get("format", {}).get("durationSeconds")
    if previous_end is not None and total != previous_end:
        errors.append(f"format duration {total} does not match transcript end {previous_end}")
    _raise(errors)


def _raise(errors: list[str]) -> None:
    if errors:
        raise ValueError("invalid video object: " + "; ".join(errors))


def _matched_families(haystack: str) -> list[str]:
    found: list[str] = []
    for family, cues in ROUTE_KEYWORDS.items():
        if any(cue in haystack for cue in cues):
            found.append(family)
    return found


def route_visual(beat_text: str, visual: dict[str, Any]) -> tuple[str, str, list[str]]:
    """Return (visual_type, renderer, matched_families) for one beat."""
    haystack = " ".join([
        str(beat_text or ""),
        str(visual.get("visual") or ""),
        str(visual.get("type") or ""),
        str(visual.get("search") or ""),
        str(visual.get("motion") or ""),
        str(visual.get("connection") or ""),
        str(visual.get("source") or ""),
    ]).lower()
    families = _matched_families(haystack)
    # An explicit Type note wins when it names a known visual type.
    declared = str(visual.get("type") or "").strip().lower().replace(" ", "_")
    if declared in VISUAL_TYPES and declared != "mixed":
        families = [declared] + [family for family in families if family != declared]
    if not families:
        families = ["stock"]  # authentic footage is the safe default, never Hunyuan
    visual_type = families[0] if len(families) == 1 else "mixed"
    renderer = _primary_renderer(families)
    return visual_type, renderer, families


def _primary_renderer(families: list[str]) -> str:
    renderers = {RENDERER_FOR_TYPE[family] for family in families}
    for renderer in MIXED_RENDERER_PRECEDENCE:
        if renderer in renderers:
            return renderer
    return "asset"


def _purpose(beat_text: str, visual: dict[str, Any], visual_type: str) -> str:
    connection = str(visual.get("connection") or "").strip()
    if connection:
        return connection[:240]
    first_line = next((line.strip() for line in str(beat_text).splitlines() if line.strip()), "")
    kind = {
        "hunyuan": "cinematic scene",
        "stock": "authentic footage",
        "product_capture": "product record",
        "motion_graphics": "graphic explanation",
        "source_capture": "authoritative source",
        "brand_end_frame": "brand resolution",
        "mixed": "composed scene",
    }[visual_type]
    return f"{kind}: {first_line[:160]}".strip()


def _camera_for(visual_type: str, visual: dict[str, Any]) -> dict[str, Any]:
    """Map beat notes onto the template-4 camera record schema."""
    motion = str(visual.get("motion") or "").lower()
    if visual_type in ("hunyuan", "stock"):
        shot_type = "wide_establishing"
    elif visual_type == "product_capture":
        shot_type = "medium"
    else:
        shot_type = "medium"
    if "track" in motion:
        movement = "tracking"
    elif "orbit" in motion:
        movement = "orbit"
    elif "pan" in motion:
        movement = "pan"
    elif "static" in motion or "still" in motion:
        movement = "static"
    elif "aerial" in motion:
        movement = "crane"
    else:
        movement = "push_in" if visual_type in ("hunyuan", "stock") else "static"
    return {
        "shot_type": shot_type,
        "movement": movement,
        "direction": "",
        "speed": "slow" if movement != "static" else "",
    }


def decide_hunyuan_mode(families: list[str], reference_assets: list[str]) -> str:
    """T2V/I2V decision policy: exact identity needs an image reference.

    - I2V: product identity, brand identity, or an explicit reference asset.
    - T2V: unconstrained environments and concept exploration.
    """
    if "product_capture" in families or "source_capture" in families or reference_assets:
        return "i2v"
    return "t2v"


def select_reference_assets(
    assets: list[dict[str, Any]], families: list[str], visual: dict[str, Any]
) -> list[str]:
    """Resolve registry assets relevant to one shot (deterministic)."""
    if not assets or not any(family in ("product_capture", "source_capture", "stock") for family in families):
        return []
    haystack = set(
        word for word in re.findall(
            r"[a-z0-9]+",
            " ".join([
                str(visual.get("visual") or ""),
                str(visual.get("search") or ""),
                str(visual.get("source") or ""),
                str(visual.get("connection") or ""),
            ]).lower(),
        ) if len(word) > 3
    )
    scored = []
    for asset in assets:
        words = set(
            word for word in re.findall(
                r"[a-z0-9]+",
                f"{asset.get('type', '')} {asset.get('path', '')} {asset.get('purpose', '')}".lower(),
            ) if len(word) > 3
        )
        scored.append((len(haystack & words), -asset.get("identity_priority", 0), asset.get("id")))
    scored.sort(reverse=True)
    return [asset_id for overlap, _, asset_id in scored[:2] if overlap > 0 and asset_id]


def compile_hunyuan_prompt(
    bible: dict[str, Any],
    recipe: dict[str, Any],
    shot: dict[str, Any],
) -> tuple[str, str]:
    """Compile Subject + Motion + Scene + ShotType + Camera + Lighting + Style
    + Atmosphere into the final generation prompt (template-4 phase 10).

    The application owns this schema; the AI may refine wording later but
    never the structure. Deterministic finishing (text, logos, UI) is never
    part of the prompt.
    """
    from services import cinematography
    from services.visual_bible import inherit_for_shot

    inherited = inherit_for_shot(bible, shot)
    subject = str(shot.get("subject") or shot.get("purpose") or "")[:200]
    detail = shot.get("motion_detail") or {}
    motion = ", ".join(part for part in (
        detail.get("subject_motion"), detail.get("environment_motion"), detail.get("camera_motion"),
    ) if part)[:200]
    scene = str(shot.get("environment") or "")[:200]
    camera = cinematography.describe_shot_language(
        shot.get("camera"), shot.get("lens"),
        {"start": "wide", "end": "hold"},
    )
    strategy = str(recipe.get("hunyuan_prompt_strategy") or "")[:160]
    prompt = (
        f"Subject: {subject}. Motion: {motion or 'natural motion'}. Scene: {scene}. "
        f"Camera: {camera or 'slow cinematic push'}. Lighting: {inherited['lighting']}. "
        f"Style: {inherited['style']}. Atmosphere: {inherited['environment']}. "
        f"Constraint: {strategy}"
    )
    return prompt[:900], DEFAULT_NEGATIVE_PROMPT


def plan_shots(
    spec: dict[str, Any],
    context: dict[str, Any] | None = None,
    use_ai: bool = True,
    bible: dict[str, Any] | None = None,
    recipe: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build an (unsaved) ShotPlan dict. Returns (plan, ai_report)."""
    from services.visual_bible import default_bible

    beats = spec.get("transcript") or []
    if not beats:
        raise ValueError("cannot plan shots for a spec with no transcript beats")
    bible = bible or default_bible()
    recipe = recipe or {}
    assets: list[dict[str, Any]] = spec.get("_assets") or spec.get("assets") or []
    visuals: dict[str, dict[str, Any]] = spec.get("_beats_visual") or spec.get("beats_visual") or {}
    shots: list[dict[str, Any]] = []
    for index, beat in enumerate(beats):
        visual = visuals.get(beat["id"], {})
        visual_type, renderer, families = route_visual(str(beat.get("text") or ""), visual)
        start, end = beat["startSeconds"], beat["endSeconds"]
        duration = end - start
        fps = spec["format"]["fps"]
        shot_id = f"shot_{index + 1:03d}"
        camera = _camera_for(visual_type, visual)
        motion_text = str(visual.get("motion") or "")[:200] or None
        references = select_reference_assets(assets, families, visual)
        shot: dict[str, Any] = {
            "id": shot_id,
            "index": index + 1,
            "startSeconds": start,
            "endSeconds": end,
            "durationSeconds": duration,
            "transcriptBeatIds": [beat["id"]],
            "purpose": _purpose(str(beat.get("text") or ""), visual, visual_type),
            "visualType": visual_type,
            "families": families,
            "subject": str(visual.get("search") or "")[:200] or None,
            "environment": str(visual.get("visual") or visual.get("search") or "")[:200] or None,
            "composition": "portrait composition for vertical video",
            "camera": camera,
            "lens": {"focal_length": "35mm", "visual_effect": "natural environmental storytelling"},
            "lighting": dict(bible.get("lighting", {})),
            "motion": motion_text,
            "motion_detail": {
                "subject_motion": "natural motion",
                "environment_motion": "ambient activity",
                "camera_motion": motion_text or ("slow push" if camera["movement"] != "static" else "static"),
            },
            "transition_in": "fade" if index == 0 else "cut",
            "transition_out": "fade" if index == len(beats) - 1 else "cut",
            "reference_assets": references,
            "hunyuan_mode": decide_hunyuan_mode(families, references),
            "finishing": {
                "renderer": renderer,
                "strategy": str(recipe.get("finishing_strategy") or "deterministic assembly"),
            },
            "continuity": {},
            "assets": _assets_for(visual_type, families, visual, beat),
            "productConnection": str(visual.get("connection") or "")[:240] or None
            if "product_capture" in families
            else None,
            "renderRequired": True,
        }
        spoken_headline = next(
            (line.strip() for line in str(beat.get("text") or "").splitlines() if line.strip()), ""
        )
        if visual_type in ("motion_graphics", "mixed", "brand_end_frame") and spoken_headline:
            shot["textOverlay"] = {
                "text": spoken_headline[:120],
                "position": "lower third",
                "animation": "fade",
            }
        if renderer == "hunyuan":
            shot["hunyuan_mode"] = decide_hunyuan_mode(families, shot["reference_assets"])
            prompt, negative = compile_hunyuan_prompt(bible, recipe, shot)
            shot["visualPrompt"] = prompt
            shot["negativePrompt"] = negative
            shot["renderProfile"] = {
                "resolution": HUNYUAN_DEFAULT_PROFILE["resolution"],
                "fps": fps,
                "frames": max(1, round(duration * fps)),
                "steps": HUNYUAN_DEFAULT_PROFILE["steps"],
                "dtype": HUNYUAN_DEFAULT_PROFILE["dtype"],
                "seed": HUNYUAN_DEFAULT_PROFILE["seed"] + index,
            }
        elif renderer in ("motion_graphics", "ffmpeg"):
            shot["renderProfile"] = {
                "resolution": HUNYUAN_DEFAULT_PROFILE["resolution"],
                "fps": fps,
                "frames": max(1, round(duration * fps)),
                "steps": 0,
                "dtype": HUNYUAN_DEFAULT_PROFILE["dtype"],
            }
        shots.append(shot)
    _attach_continuity(shots)
    ai_report = {"source": "deterministic", "notes": []}
    if use_ai and is_model_configured():
        try:
            ai_report = _enhance_with_ai(spec, shots)
        except Exception as exc:  # noqa: BLE001 - AI is assist only; never block planning
            ai_report = {"source": "deterministic", "notes": [f"AI enhancement failed: {exc}"]}
    plan = {
        "video_spec_id": spec.get("id"),
        "shots": shots,
        "total_duration_seconds": spec["format"]["durationSeconds"],
        "status": "draft",
    }
    return plan, ai_report


def _assets_for(
    visual_type: str, families: list[str], visual: dict[str, Any], beat: dict[str, Any]
) -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []
    if "stock" in families:
        query = str(visual.get("search") or visual.get("visual") or "")[:160]
        assets.append({
            "type": "stock_footage",
            "url": f"search:{query}" if query else "search:logistics freight",
            "required": False,
        })
    if "source_capture" in families:
        assets.append({
            "type": "source_capture",
            "url": str(visual.get("source") or "source:script-reference"),
            "required": True,
        })
    if "product_capture" in families:
        assets.append({
            "type": "product_capture",
            "url": "external:approved-product-library",
            "required": True,
        })
    return assets


def _attach_continuity(shots: list[dict[str, Any]]) -> None:
    style = "restrained blue and indigo, premium commercial cinematography"
    for index, shot in enumerate(shots):
        shot["continuity"] = {
            "previousShot": shots[index - 1]["id"] if index > 0 else None,
            "nextShot": shots[index + 1]["id"] if index + 1 < len(shots) else None,
            "environment": shot.get("environment"),
            "style": style,
        }


def validate_plan(spec: dict[str, Any], plan: dict[str, Any]) -> None:
    errors: list[str] = []
    shots = plan.get("shots") or []
    beats = {beat["id"]: beat for beat in (spec.get("transcript") or [])}
    if not shots:
        errors.append("plan has no shots")
        return _raise(errors)
    covered: set[str] = set()
    for shot in shots:
        start, end = shot.get("startSeconds"), shot.get("endSeconds")
        if end is None or start is None or end <= start:
            errors.append(f"shot {shot.get('id')} has a non-positive duration")
        beat_ids = shot.get("transcriptBeatIds") or []
        if not beat_ids:
            errors.append(f"shot {shot.get('id')} covers no transcript beat")
        for beat_id in beat_ids:
            if beat_id not in beats:
                errors.append(f"shot {shot.get('id')} references unknown beat {beat_id}")
            covered.add(beat_id)
        visual_type = shot.get("visualType")
        if visual_type not in VISUAL_TYPES:
            errors.append(f"shot {shot.get('id')} has an invalid visual type {visual_type!r}")
            continue
        from services import cinematography

        for camera_error in cinematography.validate_camera(shot.get("camera") or {}):
            errors.append(f"shot {shot.get('id')}: {camera_error}")
        if not shot.get("transition_in") or not shot.get("transition_out"):
            errors.append(f"shot {shot.get('id')} is missing edit transitions")
        if not isinstance(shot.get("reference_assets"), list):
            errors.append(f"shot {shot.get('id')} has no reference asset list")
        renderer = _primary_renderer(shot.get("families") or [visual_type])
        expected_renderer = RENDERER_FOR_TYPE[visual_type]
        if visual_type != "mixed" and renderer != expected_renderer:
            errors.append(f"shot {shot.get('id')} renderer {renderer} mismatches type {visual_type}")
        if visual_type == "hunyuan":
            if not str(shot.get("visualPrompt") or "").strip():
                errors.append(f"hunyuan shot {shot.get('id')} has no visual prompt")
            if not str(shot.get("negativePrompt") or "").strip():
                errors.append(f"hunyuan shot {shot.get('id')} has no negative prompt")
            if shot.get("hunyuan_mode") not in ("t2v", "i2v"):
                errors.append(f"hunyuan shot {shot.get('id')} has no T2V/I2V decision")
        for beat_id in beat_ids:
            beat = beats.get(beat_id)
            if beat and (start != beat["startSeconds"] or end != beat["endSeconds"]):
                # Shots may merge beats; single-beat shots must preserve timing exactly.
                if len(beat_ids) == 1:
                    errors.append(f"shot {shot.get('id')} does not preserve beat {beat_id} timing")
    missing = sorted(set(beats) - covered)
    if missing:
        errors.append(f"beats without a visual treatment: {', '.join(missing)}")
    total = plan.get("total_duration_seconds")
    if total != spec.get("format", {}).get("durationSeconds"):
        errors.append("plan total duration does not match the spec duration")
    _raise(errors)


def validate_claims(
    spec: dict[str, Any], plan: dict[str, Any], context: dict[str, Any] | None = None
) -> None:
    """Enforce product-boundary and source-reference rules (prompt.md section 12)."""
    context = context if context is not None else load_indataflow_context()
    forbidden = _forbidden_phrases(context)
    forbidden_res = _forbidden_patterns(context)
    errors: list[str] = []
    texts: list[tuple[str, str]] = [("spec", str(spec.get("narrative") or ""))]
    for shot in plan.get("shots") or []:
        texts.append((f"shot {shot.get('id')} purpose", str(shot.get("purpose") or "")))
        overlay = shot.get("textOverlay") or {}
        texts.append((f"shot {shot.get('id')} overlay", str(overlay.get("text") or "")))
    for location, text in texts:
        lowered = text.lower()
        for phrase in forbidden:
            if phrase and phrase.lower() in lowered:
                errors.append(f"{location} uses a prohibited claim: {phrase!r}")
        for pattern in forbidden_res:
            if pattern.search(text):
                errors.append(f"{location} matches a prohibited claim pattern: {pattern.pattern!r}")
    for shot in plan.get("shots") or []:
        if "source_capture" in (shot.get("families") or []) and not any(
            asset.get("url") for asset in (shot.get("assets") or [])
        ):
            errors.append(f"source shot {shot.get('id')} retains no source reference")
    _raise(errors)


# ---------------------------------------------------------------------------
# AI enhancement (assist only; deterministic fallback always wins on failure)
# ---------------------------------------------------------------------------


class AIEnhancedShot(BaseModel):
    shot_id: str = Field(min_length=1)
    purpose: str = Field(min_length=3, max_length=240)
    visual_prompt: str = Field(min_length=20, max_length=1200)
    negative_prompt: str = Field(min_length=10, max_length=600)
    continuity_note: str = Field(default="", max_length=240)


class AIPlanEnhancement(BaseModel):
    shots: list[AIEnhancedShot] = Field(min_length=1)


class CreativeBriefResponse(BaseModel):
    objective: str = Field(min_length=3, max_length=500)
    message: str = Field(min_length=3, max_length=500)
    audience: str = Field(default="", max_length=200)
    platform: str = Field(default="9:16", max_length=16)
    visual_style: str = Field(default="", max_length=240)
    emotional_direction: str = Field(default="", max_length=240)
    audio: str = Field(default="", max_length=240)
    runtime_seconds: int = Field(default=48, ge=5, le=300)
    title: str = Field(default="Untitled video", max_length=160)


class StoryboardBeat(BaseModel):
    narration: str = Field(min_length=1, max_length=600)
    visual: str = Field(default="", max_length=300)
    duration_seconds: float = Field(gt=0, le=60)
    purpose: str = Field(default="", max_length=240)
    source_refs: list[str] = Field(default_factory=list)


class StoryboardOutline(BaseModel):
    beats: list[StoryboardBeat] = Field(min_length=1, max_length=12)


def _enhance_with_ai(spec: dict[str, Any], shots: list[dict[str, Any]]) -> dict[str, Any]:
    from pydantic_ai import Agent, ModelRetry
    from core.models import cloud_model

    shot_ids = [shot["id"] for shot in shots]

    agent = Agent(
        cloud_model("fast"),
        output_type=AIPlanEnhancement,
        instructions=(
            "You are a visual prompt engineer for AI video generation. "
            "Refine per-shot purposes and write text-to-video prompts for the given shots. "
            "Never change timing, shot order, or factual claims; describe only what is visible. "
            "No text, watermarks, logos, dashboards or documents in generated prompts unless the "
            "shot purpose explicitly requires an overlay. Keep the restrained blue-and-indigo "
            "commercial look across shots and note continuity with neighbouring shots."
        ),
        retries=2,
    )

    @agent.output_validator
    def validate_enhancement(enhancement: AIPlanEnhancement) -> AIPlanEnhancement:
        returned = [item.shot_id for item in enhancement.shots]
        if sorted(returned) != sorted(shot_ids):
            raise ModelRetry(f"Return exactly one enhancement per shot id: {sorted(shot_ids)}.")
        return enhancement

    numbered = "\n\n".join(
        f"{shot['id']} [{shot['startSeconds']}-{shot['endSeconds']}s, {shot['visualType']}]: "
        f"{shot['purpose']}" + (
            f" Negative prompt required (generated imagery): {shot.get('negativePrompt', '')[:120]}"
            if shot["visualType"] == "hunyuan"
            else ""
        )
        for shot in shots
    )
    result = asyncio.run(agent.run(
        "Enhance these shots for the video titled "
        f"'{spec.get('title')}'. Return one entry per shot id.\n\n" + numbered
    ))
    notes: list[str] = []
    by_id = {item.shot_id: item for item in result.output.shots}
    for shot in shots:
        enhanced = by_id[shot["id"]]
        shot["purpose"] = enhanced.purpose
        shot["visualPrompt"] = enhanced.visual_prompt
        shot["negativePrompt"] = enhanced.negative_prompt
        if enhanced.continuity_note:
            shot["continuity"]["ai_note"] = enhanced.continuity_note
            notes.append(f"{shot['id']}: {enhanced.continuity_note}")
    return {"source": "ai", "notes": notes}


# ---------------------------------------------------------------------------
# RenderJob building
# ---------------------------------------------------------------------------


def build_render_jobs(
    spec: dict[str, Any], plan: dict[str, Any], *, priority: int = 100,
    render_mode: str = "shots",
) -> list[dict[str, Any]]:
    """Build RenderJob dicts (unsaved) in the requested render mode.

    - ``shots``: one RenderJob per render-required shot (clip division).
    - ``full``: a single whole-video Hunyuan job spanning the spec duration.
      The ShotPlan is still produced (timing/visual reference), but the
      queue holds one job. Note the validated worker envelope is ~81
      frames; a full-duration job exceeds it and the worker may reject it.
    """
    if render_mode not in ("shots", "full"):
        raise ValueError(f"unknown render mode: {render_mode!r} (expected 'shots' or 'full')")
    if render_mode == "full":
        return [_full_video_job(spec, plan, priority=priority)]
    jobs: list[dict[str, Any]] = []
    width, height = spec["format"]["width"], spec["format"]["height"]
    project_id = spec.get("projectId") or "project"
    for shot in plan.get("shots") or []:
        if not shot.get("renderRequired", True):
            continue
        renderer = _primary_renderer(shot.get("families") or [shot.get("visualType")])
        profile = shot.get("renderProfile") or {}
        frames = profile.get("frames") or max(1, round(shot["durationSeconds"] * spec["format"]["fps"]))
        jobs.append({
            "videoSpecId": spec.get("id"),
            "shotPlanId": plan.get("id"),
            "shotId": shot["id"],
            "priority": priority,
            "renderer": renderer,
            "hunyuan_mode": shot.get("hunyuan_mode"),
            "model": "HunyuanVideo-1.5" if renderer == "hunyuan" else None,
            "prompt": shot.get("visualPrompt"),
            "negativePrompt": shot.get("negativePrompt"),
            "inputAssets": [
                asset.get("url") for asset in (shot.get("assets") or []) if asset.get("url")
            ],
            "outputPath": f"videos/{project_id}/shots/{shot['id']}.mp4",
            "resolution": profile.get("resolution") or HUNYUAN_DEFAULT_PROFILE["resolution"],
            "width": width,
            "height": height,
            "fps": profile.get("fps") or spec["format"]["fps"],
            "frames": frames,
            "steps": profile.get("steps", HUNYUAN_DEFAULT_PROFILE["steps"]),
            "dtype": profile.get("dtype") or HUNYUAN_DEFAULT_PROFILE["dtype"],
            "seed": profile.get("seed", HUNYUAN_DEFAULT_PROFILE["seed"]),
            "continuityContext": {
                "previousShot": (shot.get("continuity") or {}).get("previousShot"),
                "nextShot": (shot.get("continuity") or {}).get("nextShot"),
                "environment": (shot.get("continuity") or {}).get("environment"),
                "style": (shot.get("continuity") or {}).get("style"),
            },
            "maxAttempts": 3,
        })
    return jobs


def _full_video_job(
    spec: dict[str, Any], plan: dict[str, Any], *, priority: int = 100
) -> dict[str, Any]:
    """One whole-video Hunyuan job: no clip division, user-chosen mode."""
    shots = plan.get("shots") or []
    beats = " / ".join(
        str(shot.get("purpose") or "")[:160] for shot in shots
    )[:700]
    prompt = (
        f"Cinematic short video, {spec.get('title')}: {beats}. "
        "Authentic freight environment, premium commercial cinematography, "
        "restrained blue and indigo visual language, realistic materials, "
        "natural motion, smooth continuous camera."
    )[:900]
    project_id = spec.get("projectId") or "project"
    total = spec["format"]["durationSeconds"]
    fps = spec["format"]["fps"]
    return {
        "videoSpecId": spec.get("id"),
        "shotPlanId": plan.get("id"),
        "shotId": "full",
        "priority": priority,
        "renderer": "hunyuan",
        "hunyuan_mode": "t2v",
        "model": "HunyuanVideo-1.5",
        "prompt": prompt,
        "negativePrompt": DEFAULT_NEGATIVE_PROMPT,
        "inputAssets": [],
        "outputPath": f"videos/{project_id}/full.mp4",
        "resolution": HUNYUAN_DEFAULT_PROFILE["resolution"],
        "width": spec["format"]["width"],
        "height": spec["format"]["height"],
        "fps": fps,
        "frames": max(1, round(total * fps)),
        "steps": HUNYUAN_DEFAULT_PROFILE["steps"],
        "dtype": HUNYUAN_DEFAULT_PROFILE["dtype"],
        "seed": HUNYUAN_DEFAULT_PROFILE["seed"],
        "continuityContext": {
            "previousShot": None,
            "nextShot": None,
            "environment": "full video, all beats",
            "style": "restrained blue and indigo, premium commercial cinematography",
        },
        "maxAttempts": 3,
    }


def validate_jobs(
    spec: dict[str, Any], plan: dict[str, Any], jobs: list[dict[str, Any]],
    *, render_mode: str = "shots",
) -> None:
    errors: list[str] = []
    if render_mode not in ("shots", "full"):
        raise ValueError(f"unknown render mode: {render_mode!r} (expected 'shots' or 'full')")
    if render_mode == "full":
        if len(jobs) != 1 or jobs[0].get("shotId") != "full":
            errors.append("full render mode expects exactly one job for shot 'full'")
            return _raise(errors)
        job = jobs[0]
        expected_frames = max(1, round(spec["format"]["durationSeconds"] * spec["format"]["fps"]))
        if job.get("frames") != expected_frames:
            errors.append(f"full job frames {job.get('frames')} != total duration x FPS ({expected_frames})")
        if job.get("seed") is None:
            errors.append("full job has no deterministic seed")
        if job.get("renderer") == "hunyuan" and not str(job.get("prompt") or "").strip():
            errors.append("full hunyuan job has no prompt")
        _raise(errors)
        return
    required = [shot for shot in (plan.get("shots") or []) if shot.get("renderRequired", True)]
    if len(jobs) != len(required):
        errors.append(
            f"expected exactly one job per render-required shot ({len(required)}), got {len(jobs)}"
        )
    paths = [job.get("outputPath") for job in jobs]
    if len(set(paths)) != len(paths):
        errors.append("render job output paths must be unique")
    by_shot = {shot["id"]: shot for shot in required}
    for job in jobs:
        shot = by_shot.get(job.get("shotId", ""))
        if not shot:
            errors.append(f"job references unknown shot {job.get('shotId')!r}")
            continue
        expected_frames = max(1, round(shot["durationSeconds"] * spec["format"]["fps"]))
        if job.get("frames") != expected_frames:
            errors.append(
                f"job for {shot['id']}: frames {job.get('frames')} != duration x FPS ({expected_frames})"
            )
        if job.get("seed") is None:
            errors.append(f"job for {shot['id']} has no deterministic seed")
        if job.get("renderer") == "hunyuan" and not str(job.get("prompt") or "").strip():
            errors.append(f"hunyuan job for {shot['id']} has no prompt")
    _raise(errors)


# ---------------------------------------------------------------------------
# High-level orchestration (CLI + API share this)
# ---------------------------------------------------------------------------


def plan_video(
    script_path: str | Path,
    *,
    project_id: str,
    campaign_id: str | None = None,
    aspect_ratio: str = "9:16",
    fps: int = 24,
    use_ai: bool = True,
) -> dict[str, Any]:
    """Parse a script file, validate, plan and persist spec + shot plan.

    Render jobs are built and validated but NOT enqueued; call
    :func:`queue_shot_plan` (or the ``queue`` CLI command) to enqueue.
    """
    from core import video_store

    video_store.init_video_db()
    path = Path(script_path)
    parsed = parse_script(path.read_text(encoding="utf-8"), source_name=path.name)
    context = load_indataflow_context()
    spec_payload = build_spec(
        parsed,
        project_id=project_id,
        campaign_id=campaign_id,
        aspect_ratio=aspect_ratio,
        fps=fps,
        source_path=str(path),
        context=context,
    )
    from services.motion_recipes import select_recipe
    from services.visual_bible import default_bible

    brief_text = " ".join([
        spec_payload.get("title", ""),
        str(spec_payload.get("narrative") or ""),
        " ".join(beat.get("text", "") for beat in parsed["beats"]),
    ])
    recipe_id, recipe = select_recipe(brief_text)
    bible = default_bible(brand_name=spec_payload.get("brand", {}).get("name", "InDataFlow"))
    return _finalize_directed_plan(
        spec_payload, context, use_ai=use_ai,
        recipe_id=recipe_id, recipe=recipe, bible=bible,
    )


def _finalize_directed_plan(
    spec_payload: dict[str, Any],
    context: dict[str, Any],
    *,
    use_ai: bool,
    recipe_id: str,
    recipe: dict[str, Any],
    bible: dict[str, Any],
) -> dict[str, Any]:
    """Shared persist path: validate, store spec/bible/assets/plan, build jobs."""
    from core import video_store
    from services.visual_bible import validate_bible

    validate_spec(spec_payload)
    validate_bible(bible)
    spec = video_store.create_spec(_store_spec_payload(spec_payload))
    spec_payload["id"] = spec["id"]
    stored_bible = video_store.save_visual_bible(spec["id"], bible, recipe_id=recipe_id)
    video_store.register_assets(spec["id"], spec_payload.get("assets") or [])
    plan_payload, ai_report = plan_shots(
        {**spec_payload, "id": spec["id"]}, context, use_ai=use_ai,
        bible=bible, recipe=recipe,
    )
    validate_plan(spec_payload, plan_payload)
    validate_claims(spec_payload, plan_payload, context)
    plan = video_store.create_shot_plan({
        "video_spec_id": spec["id"],
        "shots": plan_payload["shots"],
        "total_duration_seconds": plan_payload["total_duration_seconds"],
        "status": "planned",
    })
    video_store.update_spec_status(spec["id"], "planned")
    jobs = build_render_jobs({**spec_payload, "id": spec["id"]}, {**plan_payload, "id": plan["id"]})
    validate_jobs(spec_payload, {**plan_payload, "id": plan["id"]}, jobs)
    return {
        "spec": video_store.get_spec(spec["id"]),
        "plan": video_store.get_shot_plan(plan["id"]),
        "jobs": jobs,
        "ai": ai_report,
        "recipe": recipe_id,
        "visual_bible": stored_bible,
        "assets": video_store.list_assets(spec["id"]),
    }


def direct_brief(
    brief: str,
    *,
    project_id: str,
    campaign_id: str | None = None,
    aspect_ratio: str = "9:16",
    fps: int = 24,
) -> dict[str, Any]:
    """Direct a video from a human creative brief (template-4 phase 20).

    Requires a configured model router: the director (creative direction +
    storyboarding over OmniRoute) turns the brief into a validated outline,
    then the deterministic pipeline (recipe, bible, shots, jobs, validators)
    takes over. Transcript-wording rules do not apply here — there is no
    source script; beats carry ``source: "ai-brief"`` provenance instead.
    Raises RuntimeError when no model key is configured.
    """
    from services.creative_director import CreativeDirector, DirectorUnavailable
    from services.motion_recipes import RECIPES, select_recipe_ai
    from services.visual_bible import default_bible

    if not brief or not brief.strip():
        raise ValueError("brief must not be empty")
    try:
        creative = CreativeDirector(
            "creative_direction",
            instructions=(
                "You are a creative director turning a human brief into a production "
                "plan. Preserve the brief's factual claims verbatim; label anything "
                "you invent as an assumption in the message field."
            ),
        ).run(f"Creative brief:\n{brief[:2000]}", CreativeBriefResponse)
    except DirectorUnavailable as exc:
        raise RuntimeError(
            "brief-driven directing needs a model router key (OMNIROUTE_API_KEY). "
            "Use a prepared script with plan_video instead."
        ) from exc

    recipe_choice = select_recipe_ai(brief)
    recipe_id = recipe_choice["recipe"]
    recipe = RECIPES[recipe_id]
    bible = default_bible()

    from pydantic_ai import ModelRetry

    def _validate_outline(outline: StoryboardOutline) -> StoryboardOutline:
        total = sum(beat.duration_seconds for beat in outline.beats)
        if total <= 0:
            raise ModelRetry("Storyboard beats must have positive total duration.")
        return outline

    storyteller = CreativeDirector(
        "storyboarding",
        instructions=(
            "You are a storyboard artist. Break the approved direction into an ordered "
            "list of visual beats covering the runtime exactly once, in order. Keep "
            "narration factual per the brief; every beat needs a concrete visual."
        ),
        output_validator=_validate_outline,
    )

    direction_text = (
        f"Objective: {creative.objective}\nMessage: {creative.message}\n"
        f"Audience: {creative.audience}\nRuntime: {creative.runtime_seconds}s\n"
        f"Style: {creative.visual_style}\nEmotion: {creative.emotional_direction}"
    )
    outline = storyteller.run(
        f"{direction_text}\n\nOriginal brief:\n{brief[:2000]}", StoryboardOutline
    )

    cursor = 0.0
    beats = []
    for index, beat in enumerate(outline.beats):
        start, end = cursor, cursor + beat.duration_seconds
        cursor = end
        beats.append({
            "id": f"beat_{index + 1:02d}",
            "startSeconds": start,
            "endSeconds": end,
            "text": beat.narration,
            "source": "ai-brief",
            "visual": {
                "visual": beat.visual,
                "connection": beat.purpose,
                "source": "; ".join(beat.source_refs),
            },
        })
    context = load_indataflow_context()
    spec_payload = build_spec(
        {"title": creative.title, "meta": {
            "objective": creative.objective,
            "message": creative.message,
            "buyer": creative.audience,
            "platform": creative.platform,
            "visual_style": creative.visual_style,
            "emotional_direction": creative.emotional_direction,
            "audio": creative.audio,
            "narrative": brief[:1000],
        }, "beats": beats},
        project_id=project_id,
        campaign_id=campaign_id,
        aspect_ratio=aspect_ratio if aspect_ratio in FORMAT_SIZES else "9:16",
        fps=fps,
        source_path=None,
        context=context,
    )
    return _finalize_directed_plan(
        spec_payload, context, use_ai=True,
        recipe_id=recipe_id, recipe=recipe, bible=bible,
    )


def _store_spec_payload(spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "project_id": spec["projectId"],
        "campaign_id": spec.get("campaignId"),
        "title": spec["title"],
        "brand": spec.get("brand"),
        "format": spec.get("format"),
        "audience": spec.get("audience"),
        "narrative": spec.get("narrative"),
        "transcript": spec.get("transcript"),
        "beats_visual": spec.get("_beats_visual"),
        "visualRules": spec.get("visualRules"),
        "brandConstraints": spec.get("brandConstraints"),
        "productBoundary": spec.get("productBoundary"),
        "cta": spec.get("cta"),
        "sources": spec.get("sources"),
        "extra": spec.get("extra"),
        "sourceScriptId": spec.get("sourceScriptId"),
        "source_path": spec.get("source_path"),
        "status": "planned",
    }


def queue_shot_plan(plan_id: str, *, priority: int = 100, render_mode: str = "shots") -> dict[str, Any]:
    """Enqueue RenderJobs for a planned shot plan in the requested render mode.

    ``shots`` (default) enqueues one RenderJob per render-required shot;
    ``full`` enqueues a single whole-video Hunyuan job and skips the clip
    division. Re-queueing a plan that already has jobs returns the existing
    rows with ``already_queued=True``.
    """
    from core import video_store

    video_store.init_video_db()
    plan = video_store.get_shot_plan(plan_id)
    if not plan:
        raise ValueError(f"shot plan not found: {plan_id}")
    spec = video_store.get_spec(plan["video_spec_id"])
    if not spec:
        raise ValueError(f"video spec not found: {plan['video_spec_id']}")
    existing = video_store.list_jobs(shot_plan_id=plan_id)
    if existing:
        return {"queued": existing, "already_queued": True, "counts": _job_counts(existing, plan)}
    jobs = build_render_jobs(spec, plan, priority=priority, render_mode=render_mode)
    validate_jobs(spec, plan, jobs, render_mode=render_mode)
    queued = video_store.enqueue_jobs(_store_job_rows(jobs))
    video_store.update_plan_status(plan_id, "queued")
    video_store.update_spec_status(spec["id"], "queued")
    return {"queued": queued, "already_queued": False, "counts": _job_counts(queued, plan)}


def _store_job_rows(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for job in jobs:
        rows.append({
            "video_spec_id": job["videoSpecId"],
            "shot_plan_id": job["shotPlanId"],
            "shot_id": job["shotId"],
            "priority": job.get("priority") or 100,
            "renderer": job["renderer"],
            "hunyuan_mode": job.get("hunyuan_mode"),
            "model": job.get("model"),
            "prompt": job.get("prompt"),
            "negativePrompt": job.get("negativePrompt"),
            "inputAssets": job.get("inputAssets") or [],
            "output_path": job["outputPath"],
            "resolution": job.get("resolution"),
            "width": job.get("width"),
            "height": job.get("height"),
            "fps": job.get("fps"),
            "frames": job.get("frames"),
            "steps": job.get("steps"),
            "dtype": job.get("dtype"),
            "seed": job.get("seed"),
            "continuityContext": job.get("continuityContext"),
            "maxAttempts": job.get("maxAttempts") or 3,
        })
    return rows


def _job_counts(jobs: list[dict[str, Any]], plan: dict[str, Any] | None = None) -> dict[str, Any]:
    by_renderer: dict[str, int] = {}
    for job in jobs:
        by_renderer[job["renderer"]] = by_renderer.get(job["renderer"], 0) + 1
    queued_ids = {job.get("shotId") or job.get("shot_id") for job in jobs}
    shots_by_id = {shot.get("id"): shot for shot in ((plan or {}).get("shots") or [])} if plan else {}
    brand_end_frames = sum(
        1
        for shot_id in queued_ids
        if "brand_end_frame" in (shots_by_id.get(shot_id, {}).get("families") or [])
    )
    return {"total": len(jobs), "by_renderer": by_renderer, "brand_end_frames": brand_end_frames}


def hunyuan_profile() -> dict[str, Any]:
    """The default MI300X render profile (prompt.md section 9)."""
    return dict(HUNYUAN_DEFAULT_PROFILE)


def worker_env_example() -> dict[str, str]:
    return {
        "HUNYUAN_MODEL_PATH": "/models/HunyuanVideo-1.5",
        "AUTOEVOLVE_QUEUE_URL": "http://127.0.0.1:8787",
        "WORKER_ID": "mi300x-01",
    }


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, "") or default))
    except ValueError:
        return default
