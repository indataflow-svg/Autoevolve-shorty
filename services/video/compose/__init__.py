"""Compose entry point: pack beats become queued jobs or deterministic renders.

This is the seam the compose stage owns. A pack concept's beats split two
ways: beats with ``generate == True`` become Hunyuan jobs through the existing
queue/submit path, and every other beat waits for its deterministic renderer
(Phase 3). Nothing here generates anything: it only builds job records from
pack data, using the same shapes ``job_builder`` produces so validation,
queueing and submission behave identically.
"""
from __future__ import annotations

from typing import Any

from services.video.defs import (
    DEFAULT_NEGATIVE_PROMPT,
    FORMAT_SIZES,
    HUNYUAN_DEFAULT_PROFILE,
)

# Canvas for composed videos. The pack targets 4:5; --format may override it.
DEFAULT_ASPECT = "4:5"
DEFAULT_FPS = 24


def register_pack_concept(
    concept: Any,
    *,
    project_id: str,
    aspect_ratio: str = DEFAULT_ASPECT,
    fps: int = DEFAULT_FPS,
) -> dict[str, Any]:
    """Register a pack concept as a spec + shot plan with pack provenance.

    The pack is the source of truth, so the concept gets real parent rows
    instead of synthetic ids: jobs keep their foreign keys, history stays
    queryable, and the transcript beats are preserved verbatim on the spec.
    Every beat becomes a shot, GPU-eligible or not -- deterministic beats
    wait for their renderer (Phase 3) rather than being skipped.
    """
    from core import video_store

    width, height = FORMAT_SIZES[aspect_ratio]
    total = max((beat.t_out for beat in concept.beats), default=0.0)
    spec = video_store.create_spec({
        "project_id": project_id,
        "title": concept.title,
        "brand": {},
        "format": {
            "aspectRatio": aspect_ratio,
            "width": width,
            "height": height,
            "durationSeconds": total,
            "fps": fps,
        },
        "narrative": f"pack concept {concept.n}: buyer {concept.buyer or 'unknown'}",
        "transcript": [
            {
                "n": beat.n,
                "t_in": beat.t_in,
                "t_out": beat.t_out,
                "caption_lines": list(beat.caption_lines),
            }
            for beat in concept.beats
        ],
        "source_path": f"pack:concept-{concept.n}",
        "status": "planned",
    })
    shots = []
    for beat in concept.beats:
        # The pack's Preferred visual type routes first: it is the author's
        # explicit declaration, so it outranks keyword matching (the same
        # precedence route_visual gives a declared type). The generate flag
        # stays the GPU gate: a beat is only renderable on GPU when it both
        # asks for generated imagery and routes to the hunyuan renderer.
        from services.video.shot_planner import route_visual

        visual_type, renderer, families = route_visual(
            " ".join(beat.caption_lines),
            {
                "visual": beat.visible,
                "type": beat.preferred_type,
                "search": beat.search,
                "motion": ", ".join(beat.motion),
                "connection": beat.connection,
            },
        )
        shots.append({
            "id": f"beat_{beat.n:02d}",
            "startSeconds": beat.t_in,
            "endSeconds": beat.t_out,
            "durationSeconds": round(beat.duration, 3),
            "purpose": beat.connection or beat.visible,
            "visualType": visual_type,
            "renderer": renderer,
            "families": families,
            "visualPrompt": beat.fallback_prompt if beat.generate else beat.visible,
            "negativePrompt": DEFAULT_NEGATIVE_PROMPT if beat.generate else "",
            "renderRequired": beat.generate and renderer == "hunyuan",
            "caption_lines": list(beat.caption_lines),
            "preferred_type": beat.preferred_type,
            "search": beat.search,
            "crop_focus": beat.crop_focus,
            "motion": list(beat.motion),
            "generate": beat.generate,
            "fallback_prompt": beat.fallback_prompt,
        })
    plan = video_store.create_shot_plan({
        "video_spec_id": spec["id"],
        "shots": shots,
        "total_duration_seconds": total,
        "status": "planned",
    })
    return {"spec": spec, "plan": plan}


def gpu_jobs_for_concept(
    concept: Any,
    *,
    project_id: str,
    spec_id: str,
    plan_id: str,
    aspect_ratio: str = DEFAULT_ASPECT,
    fps: int = DEFAULT_FPS,
    priority: int = 100,
) -> list[dict[str, Any]]:
    """Build Hunyuan job dicts (unsaved) for a concept's GPU-eligible beats.

    Only beats with ``generate == True`` produce jobs: the beat's type must
    ask for generated imagery AND a usable fallback prompt must exist. The
    prompt is the pack's own fallback prompt -- that field exists for exactly
    this purpose -- so no model output ever reaches the worker.

    A ``--gpu off`` run calls this and queues nothing; ``--gpu auto`` queues
    exactly what it returns.
    """
    width, height = FORMAT_SIZES[aspect_ratio]
    jobs: list[dict[str, Any]] = []
    for beat in concept.beats:
        if not beat.generate:
            continue
        # A generate flag alone is not enough: the beat must also route to the
        # hunyuan renderer. A "generated illustration title" is a deterministic
        # draw (motion_graphics), and sending it to the GPU would spend money
        # on a raster approximation of a shape the compose stage draws exactly.
        from services.video.shot_planner import route_visual

        _, renderer, _ = route_visual(
            " ".join(beat.caption_lines),
            {
                "visual": beat.visible,
                "type": beat.preferred_type,
                "search": beat.search,
                "motion": ", ".join(beat.motion),
                "connection": beat.connection,
            },
        )
        if renderer != "hunyuan":
            continue
        if not str(beat.fallback_prompt or "").strip():
            raise ValueError(
                f"beat {beat.n} is GPU-eligible but has no fallback prompt"
            )
        frames = max(1, round(beat.duration * fps))
        jobs.append({
            "videoSpecId": spec_id,
            "shotPlanId": plan_id,
            "shotId": f"beat_{beat.n:02d}",
            "priority": priority,
            "renderer": "hunyuan",
            "hunyuan_mode": "t2v",
            "model": "HunyuanVideo-1.5",
            "prompt": str(beat.fallback_prompt).strip()[:900],
            "negativePrompt": DEFAULT_NEGATIVE_PROMPT,
            "inputAssets": [],
            "outputPath": (
                f"videos/{project_id}/beats/beat_{beat.n:02d}.mp4"
            ),
            "resolution": HUNYUAN_DEFAULT_PROFILE["resolution"],
            "width": width,
            "height": height,
            "fps": fps,
            "frames": frames,
            "steps": HUNYUAN_DEFAULT_PROFILE["steps"],
            "dtype": HUNYUAN_DEFAULT_PROFILE["dtype"],
            "seed": HUNYUAN_DEFAULT_PROFILE["seed"],
            "continuityContext": {
                "previousShot": None,
                "nextShot": None,
                "environment": f"pack beat {beat.n}: {beat.visible[:120]}",
                "style": "flat vector illustration",
            },
            "maxAttempts": 3,
        })
    return jobs
