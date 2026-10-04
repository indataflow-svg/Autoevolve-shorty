"""RenderJob building and validation (one job per shot, or one full job)."""
from __future__ import annotations

from typing import Any

from services.video.defs import DEFAULT_NEGATIVE_PROMPT, HUNYUAN_DEFAULT_PROFILE, invalid
from services.video.shot_planner import primary_renderer

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
            return invalid(errors)
        job = jobs[0]
        expected_frames = max(1, round(spec["format"]["durationSeconds"] * spec["format"]["fps"]))
        if job.get("frames") != expected_frames:
            errors.append(f"full job frames {job.get('frames')} != total duration x FPS ({expected_frames})")
        if job.get("seed") is None:
            errors.append("full job has no deterministic seed")
        if job.get("renderer") == "hunyuan" and not str(job.get("prompt") or "").strip():
            errors.append("full hunyuan job has no prompt")
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
