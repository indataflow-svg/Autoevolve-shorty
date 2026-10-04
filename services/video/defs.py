"""Shared constants and the validation-error helper for services.video."""
from __future__ import annotations

from typing import Any


def invalid(errors: list[str]) -> None:
    if errors:
        raise ValueError("invalid video object: " + "; ".join(errors))

HUNYUAN_DEFAULT_PROFILE: dict[str, Any] = {
    "resolution": "480p",
    "fps": 24,
    # Ignored when enable_step_distill is on: the distilled path substitutes
    # DISTILLED_STEPS (services.renderers) for the full denoise loop.
    "steps": 20,
    "dtype": "bf16",
    "seed": 42,
    "rewrite": False,
    # Offloading trades a little speed for VRAM headroom. Enabled because the
    # observed failures at 480/720 frames died mid-sampling rather than at load.
    "offloading": True,
    "sr": False,
    "cfg_distilled": False,
    # Step distillation collapses ~20 sampling steps into a handful. This is the
    # single largest speed lever available and it was previously defined here but
    # never transmitted to the worker, so every render paid full sampling cost.
    "enable_step_distill": True,
}

FORMAT_SIZES = {
    "4:5": (1080, 1350),
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
    "1:1": (1080, 1080),
}

# Flat graphic / vector-illustration direction. Hunyuan is a raster diffusion
# model, so this is a style bias, not true vector output: it pushes toward flat
# two-dimensional shapes, clean geometry, bold silhouettes and icon-like forms
# instead of photographic texture. Real SVG/icon rendering is the deterministic
# motion-graphics path (recipe `flat-vector-explainer`), which is not built yet.
GRAPHIC_STYLE_DIRECTION = (
    "flat 2D vector illustration style, clean geometric shapes, bold flat "
    "silhouettes, icon-like forms, crisp edges, minimal detail, limited brand "
    "palette of blue and indigo on a light neutral background, no gradients, "
    "no photorealism, no texture grain, no depth of field, even lighting"
)

# Prompt tail that adds motion to the flat graphic direction.
GRAPHIC_MOTION_DIRECTION = (
    "smooth continuous animation, elements sliding and scaling in sequence, "
    "confident easing, steady camera or gentle push, one idea per moment"
)

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
        "cityscape", "skyline", "neon", "metropolis", "futuristic city",
        "city at night", "aerial city",
        "natural landscape", "landscape", "horizon", "mountain", "desert",
        "ocean", "forest",
        # Flat graphic / icon-animation language. Hunyuan is a raster model, so
        # these do not buy true vector output, but they are the beats it can
        # actually render: without them every icon beat falls through to stock.
        "vector", "flat 2d", "icon", "illustration", "graphic",
        "motion graphics", "silhouette", "geometric", "2d",
        "minimalist", "cut-out", "papercut", "line art",
    ),
    "stock": (
        "truck", "ship", "port", "warehouse", "document", "people", "driver",
        "customs", "cargo", "container", "footage", "freight", "border",
        "crane", "highway", "corridor",
    ),
}

# Information-display cues: content that must be rendered deterministically
# (text, diagrams, data, labeled graphics), never generated. When these meet
# a hunyuan match, deterministic graphics win — generating labeled diagrams
# or data displays fabricates information.
INFO_DISPLAY_CUES = (
    "holographic projection",
    "projection of",
    "flowchart",
    "flow chart",
    "diagram",
    "infographic",
    "screen showing",
    "screen displaying",
    "data display",
    "data readout",
    "dashboard",
    "monitor",
    "displaying",
    "interface showing",
    "labeled as",
    "labels",
    "logo",
    "sign reading",
    "illuminated sign",
    "text reading",
    "tagline",
)

# Renderer precedence when a shot mixes production families: generated footage
# first, then the authored assembly (brand end cards via ffmpeg, graphics via
# the motion renderer), with acquisition (asset) as the fallback owner.
MIXED_RENDERER_PRECEDENCE = ("hunyuan", "ffmpeg", "motion_graphics", "asset")
