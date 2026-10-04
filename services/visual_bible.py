"""Project-level Visual Bible (template-4 phase 5).

One bible per spec; every generated shot inherits it so the film does not
look like a different movie in every shot. Bibles are plain dicts validated
by :func:`validate_bible` and persisted via ``video_visual_bibles``.
:func:`inherit_for_shot` renders the bible as prompt context for the
Hunyuan prompt compiler.
"""
from __future__ import annotations

from typing import Any

REQUIRED_SECTIONS = (
    "brand",
    "cinematography",
    "lighting",
    "environment",
    "motion",
    "editing",
    "visual_identity",
)


def default_bible(
    *,
    brand_name: str = "InDataFlow",
    colors: list[str] | None = None,
    style: str = "restrained blue and indigo, premium commercial cinematography",
) -> dict[str, Any]:
    return {
        "brand": {
            "colors": colors or ["#1B2A6B", "#2E5AAC", "#E8EDF7"],
            "typography": "condensed uppercase headlines",
            "logo_rules": "owned end card only; never generate logos",
            "identity_rules": f"{brand_name} appears via approved captures and the owned end card",
        },
        "cinematography": {
            "camera_language": "slow deliberate moves, one clear move per shot",
            "lens_language": "shallow depth of field, natural perspective",
            "framing": "portrait composition for vertical video",
            "depth_of_field": "shallow",
        },
        "lighting": {
            "key": "soft directional daylight",
            "fill": "cool ambient bounce",
            "contrast": "moderate",
            "color_temperature": "neutral-cool",
        },
        "environment": {
            "architecture": "authentic freight environments",
            "materials": "realistic steel, concrete, container textures",
            "atmosphere": "clear operational calm, no fantasy elements",
        },
        "motion": {
            "intensity": "restrained",
            "rhythm": "matched to narration beats",
            "acceleration": "ease in-out",
            "easing": "smooth settle on the final beat",
        },
        "editing": {
            "transition_language": "cuts; dissolves only for time passage",
            "pacing": "6-10 second shots",
            "shot_duration": "match the transcript beat exactly",
        },
        "visual_identity": {
            "realism": "photorealistic live action look",
            "stylization": "none beyond brand color restraint",
            "texture": "natural grain, no synthetic smoothing",
            "grain": "subtle",
        },
    }


def validate_bible(bible: dict[str, Any]) -> None:
    errors = [f"bible is missing section {section!r}" for section in REQUIRED_SECTIONS
              if not isinstance(bible.get(section), dict)]
    if errors:
        raise ValueError("invalid visual bible: " + "; ".join(errors))


def inherit_for_shot(bible: dict[str, Any], shot: dict[str, Any]) -> dict[str, str]:
    """Render the bible sections a shot prompt needs as short strings."""
    cine = bible.get("cinematography", {})
    light = bible.get("lighting", {})
    env = bible.get("environment", {})
    ident = bible.get("visual_identity", {})
    motion = bible.get("motion", {})
    return {
        "style": (
            f"{ident.get('realism', '')}, {cine.get('framing', '')}, "
            f"{cine.get('depth_of_field', '')} depth of field".strip(", ")
        ),
        "lighting": (
            f"{light.get('key', '')}, {light.get('fill', '')}, "
            f"{light.get('color_temperature', '')}".strip(", ")
        ),
        "environment": (
            f"{env.get('architecture', '')}, {env.get('materials', '')}, "
            f"{env.get('atmosphere', '')}".strip(", ")
        ),
        "motion": (
            f"{shot.get('motion') or motion.get('intensity', '')}, "
            f"{motion.get('rhythm', '')}".strip(", ")
        ),
    }
