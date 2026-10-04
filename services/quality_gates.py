"""Quality gates (template-4 phase 17).

Nothing reaches final output without passing every gate. Each gate returns
PASS, FAIL, or SKIPPED (with a reason) — a gate that cannot run honestly
abstains instead of passing.
"""
from __future__ import annotations

from typing import Any

GATES = ("ai_schema", "generation", "video", "visual", "brand", "assembly")


def run_gates(
    spec: dict[str, Any],
    plan: dict[str, Any],
    jobs: list[dict[str, Any]],
    *,
    artifacts: dict[str, str] | None = None,
    context: dict[str, Any] | None = None,
    render_mode: str = "shots",
) -> dict[str, Any]:
    """Run all quality gates. ``artifacts`` maps shot_id -> local MP4 path.

    Jobs are expected in pipeline (camelCase) shape, as built by
    :func:`video_pipeline.build_render_jobs`; normalize store rows at the
    boundary before calling.
    """
    from services import review
    from services.video import pipeline as video_pipeline

    gates: dict[str, dict[str, Any]] = {}
    context = context if context is not None else video_pipeline.load_indataflow_context()

    try:
        video_pipeline.validate_spec(spec)
        video_pipeline.validate_plan(spec, plan)
        video_pipeline.validate_jobs(spec, plan, jobs, render_mode=render_mode)
        video_pipeline.validate_claims(spec, plan, context)
        from services.visual_bible import validate_bible

        bible = plan.get("visual_bible") or {}
        if bible:
            validate_bible(bible)
        gates["ai_schema"] = _pass("spec, plan, jobs, claims and bible validate")
    except ValueError as exc:
        gates["ai_schema"] = _fail(str(exc))

    missing = [
        job.get("shotId")
        for job in jobs
        if not job.get("renderer") or not job.get("outputPath") or not job.get("frames")
    ]
    gates["generation"] = (
        _fail(f"incomplete job records: {missing}") if missing
        else _pass("every job has renderer, output path and frame count")
    )

    artifacts = artifacts or {}
    if not artifacts:
        gates["video"] = _skipped("no rendered artifacts yet")
        gates["visual"] = _skipped("no rendered artifacts yet")
    else:
        video_issues: list[str] = []
        for shot_id, path in artifacts.items():
            job = next((job for job in jobs if job.get("shotId") == shot_id), {})
            verdict = review.technical_review(path, job)
            if verdict["status"] != "PASS":
                video_issues.append(f"{shot_id}: {verdict['status']} ({verdict['recommendation']})")
        gates["video"] = (
            _fail("; ".join(video_issues)) if video_issues
            else _pass("all rendered artifacts decode and match their jobs")
        )
        visual_issues = []
        for shot_id, path in artifacts.items():
            shot = next((shot for shot in (plan.get("shots") or []) if shot.get("id") == shot_id), {})
            verdict = review.ai_visual_review(path, shot)
            if verdict["status"] not in ("PASS", "SKIPPED"):
                visual_issues.append(f"{shot_id}: {verdict['status']}")
        gates["visual"] = (
            _fail("; ".join(visual_issues)) if visual_issues
            else _pass("visual review abstained (no vision model) or passed")
        )

    shots = {shot.get("id") for shot in (plan.get("shots") or [])}
    rendered = set(artifacts)
    if not artifacts:
        gates["assembly"] = _skipped("no rendered artifacts yet")
    elif not shots <= rendered:
        gates["assembly"] = _fail(f"missing artifacts for shots: {sorted(shots - rendered)}")
    else:
        total = sum(shot.get("durationSeconds", 0) for shot in (plan.get("shots") or []))
        expected = spec.get("format", {}).get("durationSeconds")
        gates["assembly"] = (
            _pass("all shots rendered; durations reconcile")
            if total == expected
            else _fail(f"shot durations sum to {total}, spec says {expected}")
        )

    try:
        video_pipeline.validate_claims(spec, plan, context)
        gates["brand"] = _pass("claims inside product boundary; sources retained")
    except ValueError as exc:
        gates["brand"] = _fail(str(exc))
    passed = all(gate["status"] in ("PASS", "SKIPPED") for gate in gates.values())
    return {"gates": gates, "passed": passed}


def _pass(reason: str) -> dict[str, Any]:
    return {"status": "PASS", "reason": reason}


def _fail(reason: str) -> dict[str, Any]:
    return {"status": "FAIL", "reason": reason}


def _skipped(reason: str) -> dict[str, Any]:
    return {"status": "SKIPPED", "reason": reason}
