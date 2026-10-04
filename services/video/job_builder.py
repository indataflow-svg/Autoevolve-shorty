"""RenderJob building and validation (one job per shot, or chunked full video)."""
from __future__ import annotations

import math
import re
from typing import Any

from services.video.defs import DEFAULT_NEGATIVE_PROMPT, HUNYUAN_DEFAULT_PROFILE, invalid
from services.video.shot_planner import primary_renderer

# HunyuanVideo-1.5 generates a fixed temporal window of 129 frames (~5.4s at
# 24fps). Requesting more than that in a single denoise pass is out of
# distribution for the model, which is what the 480f timeout and the 720f
# mid-render 500 actually were. A full video is therefore N windowed chunks that
# are deterministically concatenated into one deliverable MP4.
MAX_FRAMES_PER_RENDER = 129

# Product-level art direction. True when the film should read as flat graphic /
# icon animation rather than photographic cinema. Hunyuan cannot emit real SVG,
# so this biases the prompt toward flat vector-illustration language; the
# deterministic motion-graphics renderer (not built) is what would make it true
# vector output.
GRAPHIC_STYLE = True


def build_render_jobs(
    spec: dict[str, Any], plan: dict[str, Any], *, priority: int = 100,
    render_mode: str = "shots",
    bible: dict[str, Any] | None = None, recipe: dict[str, Any] | None = None,
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
        return _full_video_chunks(spec, plan, priority=priority, bible=bible, recipe=recipe)
    jobs: list[dict[str, Any]] = []
    width, height = spec["format"]["width"], spec["format"]["height"]
    project_id = spec.get("projectId") or "project"
    for shot in plan.get("shots") or []:
        if not shot.get("renderRequired", True):
            continue
        renderer = primary_renderer(shot.get("families") or [shot.get("visualType")])
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


def _full_video_chunks(
    spec: dict[str, Any], plan: dict[str, Any], *, priority: int = 100,
    bible: dict[str, Any] | None = None, recipe: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """One whole video, as N windowed Hunyuan chunks plus a deterministic assembly.

    The user still gets a single deliverable MP4, but the model is only ever
    asked for what it can actually generate: a fixed 129-frame temporal window.
    Anything longer is chunked and concatenated by FFmpeg, which is the same
    approach ``engines/g2/g2_runtime/mixed_video.py`` already uses.
    """
    from services.visual_bible import inherit_for_shot
    from services.video.defs import GRAPHIC_MOTION_DIRECTION, GRAPHIC_STYLE_DIRECTION

    shots = plan.get("shots") or []
    beats = " / ".join(
        str(shot.get("purpose") or "")[:160] for shot in shots
    )[:700]
    bible = bible or {}
    inherited = inherit_for_shot(bible, shots[0] if shots else {})
    if GRAPHIC_STYLE:
        # Flat graphic / icon-animation look: no photographic environment or
        # lens language, just the illustration system and its motion.
        style_prompt = (
            f"{GRAPHIC_STYLE_DIRECTION}. Animated illustration: {beats}. "
            f"{GRAPHIC_MOTION_DIRECTION}."
        )
    else:
        environment = inherited["environment"] or "clean modern environment"
        inherited_style = inherited["style"] or "premium commercial cinematography"
        style_prompt = (
            f"Cinematic short video, {spec.get('title')}: {beats}. "
            f"{environment}, {inherited_style}, realistic materials, "
            "natural motion, smooth continuous camera."
        )

    project_id = spec.get("projectId") or "project"
    total = spec["format"]["durationSeconds"]
    fps = spec["format"]["fps"]
    total_frames = max(1, round(total * fps))
    count = max(1, math.ceil(total_frames / MAX_FRAMES_PER_RENDER))
    # Even split so no chunk is out of distribution; the tail takes the remainder.
    base = total_frames // count
    remainder = total_frames - base * count

    chunks: list[dict[str, Any]] = []
    for index in range(count):
        frames = base + (1 if index < remainder else 0)
        prompt = style_prompt[:820] + (
            f" Segment {index + 1} of {count}."
            if count > 1 else ""
        )
        chunks.append({
            "videoSpecId": spec.get("id"),
            "shotPlanId": plan.get("id"),
            "shotId": f"chunk_{index + 1:02d}",
            "priority": priority,
            "renderer": "hunyuan",
            "hunyuan_mode": "t2v",
            "model": "HunyuanVideo-1.5",
            "prompt": prompt[:900],
            "negativePrompt": DEFAULT_NEGATIVE_PROMPT,
            "inputAssets": [],
            "outputPath": f"videos/{project_id}/chunks/chunk_{index + 1:03d}.mp4",
            "resolution": HUNYUAN_DEFAULT_PROFILE["resolution"],
            "width": spec["format"]["width"],
            "height": spec["format"]["height"],
            "fps": fps,
            "frames": frames,
            "steps": HUNYUAN_DEFAULT_PROFILE["steps"],
            "dtype": HUNYUAN_DEFAULT_PROFILE["dtype"],
            # Derive a distinct but reproducible seed per chunk so a chunk can be
            # re-rendered alone and still reproduce.
            "seed": HUNYUAN_DEFAULT_PROFILE["seed"] + index,
            "continuityContext": {
                "previousShot": None,
                "nextShot": None,
                "environment": f"full video segment {index + 1} of {count}",
                "style": "restrained blue and indigo, flat graphic illustration",
            },
            "assembly": {
                "role": "chunk",
                "order": index,
                "of": count,
                "final_path": f"videos/{project_id}/full.mp4",
            },
            "maxAttempts": 3,
        })
    return chunks


def _chunk_order(job: dict[str, Any]) -> int:
    """Chunk sequence position, derived from the persisted shot id.

    ``assembly`` is a build-time convenience and does not survive the store
    round-trip, so the ordering must be recoverable from a column that does.
    """
    assembly = job.get("assembly") or {}
    if isinstance(assembly, dict) and isinstance(assembly.get("order"), int):
        return assembly["order"]
    match = re.match(r"chunk_(\d+)$", str(job.get("shotId") or ""))
    return int(match.group(1)) - 1 if match else -1


def validate_jobs(
    spec: dict[str, Any], plan: dict[str, Any], jobs: list[dict[str, Any]],
    *, render_mode: str = "shots",
) -> None:
    errors: list[str] = []
    if render_mode not in ("shots", "full"):
        raise ValueError(f"unknown render mode: {render_mode!r} (expected 'shots' or 'full')")
    if render_mode == "full":
        if not jobs:
            errors.append("full render mode produced no jobs")
            return invalid(errors)
        expected_total = max(
            1, round(spec["format"]["durationSeconds"] * spec["format"]["fps"])
        )
        orders = sorted(_chunk_order(job) for job in jobs)
        if orders != list(range(len(jobs))):
            errors.append(f"full video chunks must be ordered 0..n-1, got {orders}")
        total = 0
        for job in jobs:
            label = job.get("shotId")
            frames = job.get("frames") or 0
            total += frames
            if frames > MAX_FRAMES_PER_RENDER:
                errors.append(
                    f"chunk {label}: {frames} frames exceeds the model window "
                    f"({MAX_FRAMES_PER_RENDER})"
                )
            if frames <= 0:
                errors.append(f"chunk {label}: non-positive frame count")
            if job.get("seed") is None:
                errors.append(f"chunk {label} has no deterministic seed")
            if job.get("renderer") == "hunyuan" and not str(job.get("prompt") or "").strip():
                errors.append(f"chunk {label} hunyuan job has no prompt")
        if total != expected_total:
            errors.append(
                f"chunks total {total} frames != duration x FPS ({expected_total})"
            )
        invalid(errors)
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
    invalid(errors)


# ---------------------------------------------------------------------------
# High-level orchestration (CLI + API share this)
# ---------------------------------------------------------------------------
