"""VideoSpec building and validation (transcript wording never rewritten)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from services.video.defs import FORMAT_SIZES, invalid

KNOWLEDGE_DIR = (
    Path(__file__).parent.parent.parent / "engines" / "g1" / "knowledge" / "_drafts" / "indataflow"
)
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


def forbidden_phrases(context: dict[str, Any]) -> list[str]:
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


def forbidden_patterns(context: dict[str, Any]) -> list["re.Pattern[str]"]:
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
        return invalid(errors)
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
    invalid(errors)
