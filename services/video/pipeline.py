"""High-level orchestration: plan_video, direct_brief, queue, launch."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

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
from services.video.script_parser import parse_script
from services.video.shot_planner import plan_shots, validate_claims, validate_plan
from services.video.spec_builder import build_spec, load_indataflow_context, validate_spec

class CreativeBriefResponse(BaseModel):
    objective: str = Field(min_length=3, max_length=500)
    message: str = Field(min_length=3, max_length=500)
    audience: str = Field(default="", max_length=200)
    platform: str = Field(default="9:16", max_length=16)
    visual_style: str = Field(default="", max_length=240)
    emotional_direction: str = Field(default="", max_length=240)
    audio: str = Field(default="", max_length=240)
    runtime_seconds: int = Field(default=48, ge=5, le=300)
    title: str = Field(default="Untitled video", max_length=160)


class StoryboardBeat(BaseModel):
    narration: str = Field(min_length=1, max_length=600)
    visual: str = Field(default="", max_length=300)
    duration_seconds: float = Field(gt=0, le=60)
    purpose: str = Field(default="", max_length=240)
    source_refs: list[str] = Field(default_factory=list)


class StoryboardOutline(BaseModel):
    beats: list[StoryboardBeat] = Field(min_length=1, max_length=12)

def plan_video(
    script_path: str | Path,
    *,
    project_id: str,
    campaign_id: str | None = None,
    aspect_ratio: str = "9:16",
    fps: int = 24,
    use_ai: bool = True,
    extra_assets: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Parse a script file, validate, plan and persist spec + shot plan.

    Render jobs are built and validated but NOT enqueued; call
    :func:`queue_shot_plan` (or the ``queue`` CLI command) to enqueue.
    ``extra_assets`` (e.g. user-supplied product footage) are registered
    alongside script-derived assets before shot planning, so reference
    resolution sees them.
    """
    from core import video_store

    video_store.init_video_db()
    path = Path(script_path)
    parsed = parse_script(path.read_text(encoding="utf-8"), source_name=path.name)
    context = load_indataflow_context()
    spec_payload = build_spec(
        parsed,
        project_id=project_id,
        campaign_id=campaign_id,
        aspect_ratio=aspect_ratio,
        fps=fps,
        source_path=str(path),
        context=context,
    )
    from services.motion_recipes import select_recipe
    from services.visual_bible import default_bible

    brief_text = " ".join([
        spec_payload.get("title", ""),
        str(spec_payload.get("narrative") or ""),
        " ".join(beat.get("text", "") for beat in parsed["beats"]),
    ])
    recipe_id, recipe = select_recipe(brief_text)
    bible = default_bible(brand_name=spec_payload.get("brand", {}).get("name", "InDataFlow"))
    if extra_assets:
        spec_payload["assets"] = (spec_payload.get("assets") or []) + list(extra_assets)
    return _finalize_directed_plan(
        spec_payload, context, use_ai=use_ai,
        recipe_id=recipe_id, recipe=recipe, bible=bible,
    )


def _finalize_directed_plan(
    spec_payload: dict[str, Any],
    context: dict[str, Any],
    *,
    use_ai: bool,
    recipe_id: str,
    recipe: dict[str, Any],
    bible: dict[str, Any],
) -> dict[str, Any]:
    """Shared persist path: validate, store spec/bible/assets/plan, build jobs."""
    from core import video_store
    from services.visual_bible import validate_bible

    validate_spec(spec_payload)
    validate_bible(bible)
    spec = video_store.create_spec(store_spec_payload(spec_payload))
    spec_payload["id"] = spec["id"]
    stored_bible = video_store.save_visual_bible(spec["id"], bible, recipe_id=recipe_id)
    video_store.register_assets(spec["id"], spec_payload.get("assets") or [])
    plan_payload, ai_report = plan_shots(
        {**spec_payload, "id": spec["id"]}, context, use_ai=use_ai,
        bible=bible, recipe=recipe,
    )
    validate_plan(spec_payload, plan_payload)
    validate_claims(spec_payload, plan_payload, context)
    plan = video_store.create_shot_plan({
        "video_spec_id": spec["id"],
        "shots": plan_payload["shots"],
        "total_duration_seconds": plan_payload["total_duration_seconds"],
        "status": "planned",
    })
    video_store.update_spec_status(spec["id"], "planned")
    jobs = build_render_jobs({**spec_payload, "id": spec["id"]}, {**plan_payload, "id": plan["id"]})
    validate_jobs(spec_payload, {**plan_payload, "id": plan["id"]}, jobs)
    return {
        "spec": video_store.get_spec(spec["id"]),
        "plan": video_store.get_shot_plan(plan["id"]),
        "jobs": jobs,
        "ai": ai_report,
        "recipe": recipe_id,
        "visual_bible": stored_bible,
        "assets": video_store.list_assets(spec["id"]),
    }


def direct_brief(
    brief: str,
    *,
    project_id: str,
    campaign_id: str | None = None,
    aspect_ratio: str = "9:16",
    fps: int = 24,
) -> dict[str, Any]:
    """Direct a video from a human creative brief (template-4 phase 20).

    Requires a configured model router: the director (creative direction +
    storyboarding over OmniRoute) turns the brief into a validated outline,
    then the deterministic pipeline (recipe, bible, shots, jobs, validators)
    takes over. Transcript-wording rules do not apply here — there is no
    source script; beats carry ``source: "ai-brief"`` provenance instead.
    Raises RuntimeError when no model key is configured.
    """
    from services.creative_director import CreativeDirector, DirectorUnavailable
    from services.motion_recipes import RECIPES, select_recipe_ai
    from services.visual_bible import default_bible

    if not brief or not brief.strip():
        raise ValueError("brief must not be empty")
    try:
        creative = CreativeDirector(
            "creative_direction",
            instructions=(
                "You are a creative director turning a human brief into a production "
                "plan. Preserve the brief's factual claims verbatim; label anything "
                "you invent as an assumption in the message field."
            ),
        ).run(f"Creative brief:\n{brief[:2000]}", CreativeBriefResponse)
    except DirectorUnavailable as exc:
        raise RuntimeError(
            "brief-driven directing needs a model router key (OMNIROUTE_API_KEY). "
            "Use a prepared script with plan_video instead."
        ) from exc

    recipe_choice = select_recipe_ai(brief)
    recipe_id = recipe_choice["recipe"]
    recipe = RECIPES[recipe_id]
    bible = default_bible()

    from pydantic_ai import ModelRetry

    def _validate_outline(outline: StoryboardOutline) -> StoryboardOutline:
        total = sum(beat.duration_seconds for beat in outline.beats)
        if total <= 0:
            raise ModelRetry("Storyboard beats must have positive total duration.")
        return outline

    storyteller = CreativeDirector(
        "storyboarding",
        instructions=(
            "You are a storyboard artist. Break the approved direction into an ordered "
            "list of visual beats covering the runtime exactly once, in order. Keep "
            "narration factual per the brief; every beat needs a concrete visual."
        ),
        output_validator=_validate_outline,
    )

    direction_text = (
        f"Objective: {creative.objective}\nMessage: {creative.message}\n"
        f"Audience: {creative.audience}\nRuntime: {creative.runtime_seconds}s\n"
        f"Style: {creative.visual_style}\nEmotion: {creative.emotional_direction}"
    )
    outline = storyteller.run(
        f"{direction_text}\n\nOriginal brief:\n{brief[:2000]}", StoryboardOutline
    )

    cursor = 0.0
    beats = []
    for index, beat in enumerate(outline.beats):
        start, end = cursor, cursor + beat.duration_seconds
        cursor = end
        beats.append({
            "id": f"beat_{index + 1:02d}",
            "startSeconds": start,
            "endSeconds": end,
            "text": beat.narration,
            "source": "ai-brief",
            "visual": {
                "visual": beat.visual,
                "connection": beat.purpose,
                "source": "; ".join(beat.source_refs),
            },
        })
    context = load_indataflow_context()
    spec_payload = build_spec(
        {"title": creative.title, "meta": {
            "objective": creative.objective,
            "message": creative.message,
            "buyer": creative.audience,
            "platform": creative.platform,
            "visual_style": creative.visual_style,
            "emotional_direction": creative.emotional_direction,
            "audio": creative.audio,
            "narrative": brief[:1000],
        }, "beats": beats},
        project_id=project_id,
        campaign_id=campaign_id,
        aspect_ratio=aspect_ratio if aspect_ratio in FORMAT_SIZES else "9:16",
        fps=fps,
        source_path=None,
        context=context,
    )
    return _finalize_directed_plan(
        spec_payload, context, use_ai=True,
        recipe_id=recipe_id, recipe=recipe, bible=bible,
    )


def store_spec_payload(spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "project_id": spec["projectId"],
        "campaign_id": spec.get("campaignId"),
        "title": spec["title"],
        "brand": spec.get("brand"),
        "format": spec.get("format"),
        "audience": spec.get("audience"),
        "narrative": spec.get("narrative"),
        "transcript": spec.get("transcript"),
        "beats_visual": spec.get("_beats_visual"),
        "visualRules": spec.get("visualRules"),
        "brandConstraints": spec.get("brandConstraints"),
        "productBoundary": spec.get("productBoundary"),
        "cta": spec.get("cta"),
        "sources": spec.get("sources"),
        "extra": spec.get("extra"),
        "sourceScriptId": spec.get("sourceScriptId"),
        "source_path": spec.get("source_path"),
        "status": "planned",
    }


def queue_shot_plan(plan_id: str, *, priority: int = 100, render_mode: str = "shots") -> dict[str, Any]:
    """Enqueue RenderJobs for a planned shot plan in the requested render mode.

    ``shots`` (default) enqueues one RenderJob per render-required shot;
    ``full`` enqueues a single whole-video Hunyuan job and skips the clip
    division. Re-queueing a plan that already has jobs returns the existing
    rows with ``already_queued=True``.
    """
    from core import video_store

    video_store.init_video_db()
    plan = video_store.get_shot_plan(plan_id)
    if not plan:
        raise ValueError(f"shot plan not found: {plan_id}")
    spec = video_store.get_spec(plan["video_spec_id"])
    if not spec:
        raise ValueError(f"video spec not found: {plan['video_spec_id']}")
    existing = video_store.list_jobs(shot_plan_id=plan_id)
    if existing:
        return {"queued": existing, "already_queued": True, "counts": job_counts(existing, plan)}
    jobs = build_render_jobs(spec, plan, priority=priority, render_mode=render_mode)
    validate_jobs(spec, plan, jobs, render_mode=render_mode)
    queued = video_store.enqueue_jobs(store_job_rows(jobs))
    video_store.update_plan_status(plan_id, "queued")
    video_store.update_spec_status(spec["id"], "queued")
    return {"queued": queued, "already_queued": False, "counts": job_counts(queued, plan)}


def store_job_rows(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for job in jobs:
        rows.append({
            "video_spec_id": job["videoSpecId"],
            "shot_plan_id": job["shotPlanId"],
            "shot_id": job["shotId"],
            "priority": job.get("priority") or 100,
            "renderer": job["renderer"],
            "hunyuan_mode": job.get("hunyuan_mode"),
            "model": job.get("model"),
            "prompt": job.get("prompt"),
            "negativePrompt": job.get("negativePrompt"),
            "inputAssets": job.get("inputAssets") or [],
            "output_path": job["outputPath"],
            "resolution": job.get("resolution"),
            "width": job.get("width"),
            "height": job.get("height"),
            "fps": job.get("fps"),
            "frames": job.get("frames"),
            "steps": job.get("steps"),
            "dtype": job.get("dtype"),
            "seed": job.get("seed"),
            "continuityContext": job.get("continuityContext"),
            "maxAttempts": job.get("maxAttempts") or 3,
        })
    return rows


def job_counts(jobs: list[dict[str, Any]], plan: dict[str, Any] | None = None) -> dict[str, Any]:
    by_renderer: dict[str, int] = {}
    for job in jobs:
        by_renderer[job["renderer"]] = by_renderer.get(job["renderer"], 0) + 1
    queued_ids = {job.get("shotId") or job.get("shot_id") for job in jobs}
    shots_by_id = {shot.get("id"): shot for shot in ((plan or {}).get("shots") or [])} if plan else {}
    brand_end_frames = sum(
        1
        for shot_id in queued_ids
        if "brand_end_frame" in (shots_by_id.get(shot_id, {}).get("families") or [])
    )
    return {"total": len(jobs), "by_renderer": by_renderer, "brand_end_frames": brand_end_frames}


def hunyuan_profile() -> dict[str, Any]:
    """The default MI300X render profile (prompt.md section 9)."""
    return dict(HUNYUAN_DEFAULT_PROFILE)


def worker_env_example() -> dict[str, str]:
    return {
        "HUNYUAN_MODEL_PATH": "/models/HunyuanVideo-1.5",
        "AUTOEVOLVE_QUEUE_URL": "http://127.0.0.1:8787",
        "WORKER_ID": "mi300x-01",
    }


def reference_asset(path: str | Path) -> dict[str, Any]:
    """Build a product-reference registry entry for a user-supplied file."""
    file_path = Path(path)
    if not file_path.is_file():
        raise ValueError(f"reference not found: {path}")
    return {
        "id": f"ref_{file_path.stem[:24]}",
        "type": "product_capture",
        "path": str(file_path),
        "purpose": f"approved product reference: {file_path.name}",
        "identity_priority": 10,
        "preserve": ["product_shape", "product_color", "typography"],
        "allowed_changes": ["crop", "caption overlay"],
    }


def launch(
    *,
    brief: str | None = None,
    script_path: str | Path | None = None,
    project_id: str,
    campaign_id: str | None = None,
    aspect_ratio: str = "9:16",
    fps: int = 24,
    references: list[str | Path] | None = None,
    submit: bool = True,
    timeout_seconds: int | None = None,
    render_mode: str = "shots",
) -> dict[str, Any]:
    """Run the product-launch pipeline end to end (motion-designer.md).

    Plan (brief or script) -> queue -> submit hunyuan jobs -> gates, then
    return the launch report. Non-hunyuan jobs are recorded pending (their
    renderers are not dispatched in this phase). Exactly one of ``brief``
    and ``script_path`` is required.
    """
    from core import video_store
    from services import quality_gates, renderers

    if bool(brief) == bool(script_path):
        raise ValueError("launch needs exactly one of brief= or script_path=")
    extra_assets = [reference_asset(path) for path in (references or [])]
    if brief is not None:
        planned = direct_brief(brief, project_id=project_id, aspect_ratio=aspect_ratio, fps=fps)
        if extra_assets:
            video_store.register_assets(planned["spec"]["id"], extra_assets)
            planned["assets"] = video_store.list_assets(planned["spec"]["id"])
    else:
        assert script_path is not None
        planned = plan_video(
            script_path, project_id=project_id, campaign_id=campaign_id,
            aspect_ratio=aspect_ratio, fps=fps,
            extra_assets=extra_assets or None,
        )
    plan_id = planned["plan"]["id"]
    queued = queue_shot_plan(plan_id, render_mode=render_mode)
    submissions: list[dict[str, Any]] = []
    if submit:
        for job in queued["queued"]:
            if job["renderer"] != "hunyuan" or job["status"] != "pending":
                submissions.append({
                    "job_id": job["id"], "submitted": False,
                    "reason": f"renderer {job['renderer']} is not dispatched in this phase",
                })
                continue
            try:
                completed = renderers.submit_hunyuan_job(job["id"], timeout_seconds=timeout_seconds)
                result = completed.get("result") or {}
                submissions.append({
                    "job_id": job["id"], "submitted": True, "ok": True,
                    "output": result.get("outputPath"),
                    "sha256": (result.get("metadata") or {}).get("sha256"),
                })
            except renderers.RenderWorkerError as exc:
                submissions.append({
                    "job_id": job["id"], "submitted": True, "ok": False,
                    "kind": exc.kind, "retryable": exc.retryable, "message": str(exc)[:300],
                })
    stored_jobs = video_store.list_jobs(shot_plan_id=plan_id)
    artifacts = {
        job["shot_id"]: (job.get("result") or {}).get("outputPath")
        for job in stored_jobs
        if job["status"] == "completed" and (job.get("result") or {}).get("outputPath")
    }
    # Gates take pipeline-shape (camelCase) jobs; normalize at the boundary.
    gate_jobs = [{
        "shotId": job.get("shot_id"),
        "outputPath": job.get("output_path"),
        "frames": job.get("frames"),
        "seed": job.get("seed"),
        "renderer": job.get("renderer"),
        "prompt": job.get("prompt"),
    } for job in stored_jobs]
    gates = quality_gates.run_gates(planned["spec"], planned["plan"], gate_jobs, artifacts=artifacts)
    submitted_ok = [item.get("ok", True) for item in submissions if item.get("submitted")]
    return {
        "spec_id": planned["spec"]["id"],
        "shot_plan_id": plan_id,
        "recipe": planned.get("recipe"),
        "render_mode": render_mode,
        "counts": queued["counts"],
        "already_queued": queued["already_queued"],
        "references": [asset["path"] for asset in planned.get("assets") or []],
        "submissions": submissions,
        "artifacts": artifacts,
        "gates": gates["gates"],
        "passed": gates["passed"] and all(submitted_ok),
    }
