"""Shared constants and the validation-error helper for services.video."""
from __future__ import annotations

from typing import Any


def invalid(errors: list[str]) -> None:
    if errors:
        raise ValueError("invalid video object: " + "; ".join(errors))

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
