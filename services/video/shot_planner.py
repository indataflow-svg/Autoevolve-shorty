"""Shot planning: routing, storyboard records, prompt compiler, validators."""
from __future__ import annotations

import asyncio
import re
from typing import Any

from pydantic import BaseModel, Field

from core.models import is_model_configured

from services.video.defs import (
    DEFAULT_NEGATIVE_PROMPT,
    HUNYUAN_DEFAULT_PROFILE,
    INFO_DISPLAY_CUES,
    MIXED_RENDERER_PRECEDENCE,
    RENDERER_FOR_TYPE,
    ROUTE_KEYWORDS,
    VISUAL_TYPES,
    invalid,
)

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
    if "hunyuan" in families and any(cue in haystack for cue in INFO_DISPLAY_CUES):
        # Information displays (labeled diagrams, data projections, screens
        # showing content) must be rendered deterministically even when the
        # setting sounds cinematic: generating them fabricates information.
        families = ["motion_graphics"] + [family for family in families if family != "hunyuan"]
    if not families:
        families = ["stock"]  # authentic footage is the safe default, never Hunyuan
    visual_type = families[0] if len(families) == 1 else "mixed"
    renderer = primary_renderer(families)
    return visual_type, renderer, families


def primary_renderer(families: list[str]) -> str:
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
        return invalid(errors)
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
        renderer = primary_renderer(shot.get("families") or [visual_type])
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
    invalid(errors)


def validate_claims(
    spec: dict[str, Any], plan: dict[str, Any], context: dict[str, Any] | None = None
) -> None:
    """Enforce product-boundary and source-reference rules (prompt.md section 12)."""
    from services.video.spec_builder import forbidden_phrases, forbidden_patterns, load_indataflow_context

    context = context if context is not None else load_indataflow_context()
    forbidden = forbidden_phrases(context)
    forbidden_res = forbidden_patterns(context)
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
    invalid(errors)


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
