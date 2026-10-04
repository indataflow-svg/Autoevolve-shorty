"""Structured cinematography library (template-4 phase 7).

Lens terminology is a compositional and generation prior, not a claim that
Hunyuan physically simulates cinema lenses. Every shot carries explicit
camera/lens/framing records; :func:`describe_shot_language` compiles them
into prompt fragments for the Hunyuan prompt compiler.
"""
from __future__ import annotations

from typing import Any

SHOT_TYPES = (
    "wide_establishing",
    "full",
    "medium",
    "medium_close",
    "closeup",
    "macro",
    "overhead",
    "low_angle",
    "high_angle",
    "aerial",
)

CAMERA_MOVEMENTS = (
    "static",
    "dolly_in",
    "dolly_out",
    "tracking",
    "orbit",
    "pan",
    "tilt",
    "crane",
    "push_in",
    "pull_out",
    "macro_push",
    "reveal",
    "parallax",
)

LENSES = {
    "24mm": "expansive wide establishing views",
    "35mm": "natural environmental storytelling",
    "50mm": "neutral realistic perspective",
    "85mm": "compressed portraits with soft separation",
    "100mm_macro": "extreme detail with shallow falloff",
}

LIGHTING = (
    "soft directional daylight",
    "overcast softbox",
    "golden hour",
    "blue hour",
    "studio soft key",
    "available-light documentary",
    "high-contrast commercial",
)

DEPTH_OF_FIELD = ("deep", "moderate", "shallow")

COMPOSITION = (
    "centered subject",
    "rule of thirds",
    "leading lines",
    "symmetric",
    "portrait composition for vertical video",
)

TRANSITIONS = ("cut", "dissolve", "fade", "match_cut", "graphic_wipe", "whip_pan")

MOTION_PATTERNS = (
    "slow push settling on the final beat",
    "lateral drift then settle",
    "tracking alongside the subject",
    "static with environmental motion",
    "orbit revealing context",
    "aerial descent into the scene",
)


def validate_camera(camera: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if camera.get("shot_type") and camera["shot_type"] not in SHOT_TYPES:
        errors.append(f"unknown shot type: {camera['shot_type']!r}")
    if camera.get("movement") and camera["movement"] not in CAMERA_MOVEMENTS:
        errors.append(f"unknown camera movement: {camera['movement']!r}")
    return errors


def describe_shot_language(
    camera: dict[str, Any] | None,
    lens: dict[str, Any] | None,
    framing: dict[str, Any] | None,
) -> str:
    """Compile camera/lens/framing records into a prompt fragment."""
    parts: list[str] = []
    camera = camera or {}
    if camera.get("shot_type"):
        parts.append(str(camera["shot_type"]).replace("_", " "))
    movement = str(camera.get("movement") or "").replace("_", " ")
    direction = str(camera.get("direction") or "").strip()
    speed = str(camera.get("speed") or "").strip()
    if movement and movement != "static":
        move = movement + (f" {direction}" if direction else "") + (f", {speed}" if speed else "")
        parts.append(move.strip())
    lens = lens or {}
    focal = str(lens.get("focal_length") or "").strip()
    if focal:
        effect = LENSES.get(focal, str(lens.get("visual_effect") or "")).strip()
        parts.append(f"{focal} lens ({effect})" if effect else f"{focal} lens")
    framing = framing or {}
    start = str(framing.get("start") or "").strip()
    end = str(framing.get("end") or "").strip()
    if start or end:
        parts.append(f"framing from {start or 'wide'} to {end or 'hold'}")
    return ", ".join(part for part in parts if part)
