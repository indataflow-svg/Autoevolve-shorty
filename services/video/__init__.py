"""VideoSpec -> ShotPlan -> RenderJob pipeline (control plane side).

Split from the former ``services/video_pipeline.py`` god-module so each
stage lives in its own file: parsing, spec building, shot planning, job
building, and high-level orchestration. Import from here
(``from services.video import pipeline``) or from the stage modules
directly; ``services.video_pipeline`` no longer exists.

The pipeline is deterministic by default: parsing, validation, visual-type
routing, frame math, output paths and seeds never need a model. When a model
router key is configured (``OMNIROUTE_API_KEY``), the AI layer refines visual
prompts and continuity notes; every AI call has a deterministic fallback, the
same pattern as ``services/asset_scene_planner.py``.

Nothing here renders anything. Render jobs are queue records consumed by the
external MI300X worker (see docs/video-pipeline.md).
"""
from services.video.defs import (
    DEFAULT_NEGATIVE_PROMPT,
    FORMAT_SIZES,
    HUNYUAN_DEFAULT_PROFILE,
    MIXED_RENDERER_PRECEDENCE,
    RENDERER_FOR_TYPE,
    ROUTE_KEYWORDS,
    VISUAL_TYPES,
)
from services.video.job_builder import build_render_jobs, validate_jobs
from services.video.pipeline import (
    CreativeBriefResponse,
    StoryboardBeat,
    StoryboardOutline,
    direct_brief,
    hunyuan_profile,
    launch,
    plan_video,
    queue_shot_plan,
    reference_asset,
    worker_env_example,
)
from services.video.script_parser import (
    format_timestamp,
    parse_beat_range,
    parse_script,
    parse_timestamp,
)
from services.video.shot_planner import (
    AIPlanEnhancement,
    compile_hunyuan_prompt,
    decide_hunyuan_mode,
    plan_shots,
    primary_renderer,
    route_visual,
    select_reference_assets,
    validate_claims,
    validate_plan,
)
from services.video.spec_builder import build_spec, load_indataflow_context, validate_spec

__all__ = [
    "DEFAULT_NEGATIVE_PROMPT",
    "FORMAT_SIZES",
    "HUNYUAN_DEFAULT_PROFILE",
    "MIXED_RENDERER_PRECEDENCE",
    "RENDERER_FOR_TYPE",
    "ROUTE_KEYWORDS",
    "VISUAL_TYPES",
    "AIPlanEnhancement",
    "CreativeBriefResponse",
    "StoryboardBeat",
    "StoryboardOutline",
    "build_render_jobs",
    "build_spec",
    "compile_hunyuan_prompt",
    "decide_hunyuan_mode",
    "direct_brief",
    "format_timestamp",
    "hunyuan_profile",
    "launch",
    "load_indataflow_context",
    "parse_beat_range",
    "parse_script",
    "parse_timestamp",
    "plan_shots",
    "plan_video",
    "primary_renderer",
    "queue_shot_plan",
    "reference_asset",
    "route_visual",
    "select_reference_assets",
    "validate_claims",
    "validate_jobs",
    "validate_plan",
    "validate_spec",
    "worker_env_example",
]
