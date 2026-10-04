"""Video pipeline API: specs, shot plans and the render-job queue.

Read routes and the worker lease protocol sit behind dashboard auth. Writes
that spend GPU budget (planning a script, queueing jobs, retrying failures)
require the founder action token, the same gate as the sales/marketing action
routers. The external MI300X worker authenticates with the dashboard
credentials and only ever calls the ``/render-jobs`` worker routes.
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.sales_api import verify_founder_action
from core import video_store
from services import video_pipeline

router = APIRouter(prefix="/company/video", tags=["video"])
action_router = APIRouter(prefix="/company/video", tags=["video-actions"])
worker_router = APIRouter(prefix="/company/video", tags=["video-worker"])


def _lease_seconds() -> int:
    try:
        return max(10, int(os.getenv("VIDEO_QUEUE_LEASE_SECONDS", "") or 300))
    except ValueError:
        return 300


class SpecCreate(BaseModel):
    script_text: str = Field(min_length=1, max_length=200000)
    project_id: str = Field(min_length=1, max_length=120)
    campaign_id: str | None = Field(default=None, max_length=120)
    aspect_ratio: str = Field(default="9:16", max_length=8)
    fps: int = Field(default=24, ge=1, le=120)
    source_name: str = Field(default="script", max_length=160)


class PlanCreate(BaseModel):
    spec_id: str = Field(min_length=1, max_length=64)


class JobComplete(BaseModel):
    result: dict[str, Any] = Field(default_factory=dict)


class JobFail(BaseModel):
    code: str | None = None
    message: str = Field(default="", max_length=2000)
    retryable: bool = True


def _not_found(entity: str, identifier: str) -> HTTPException:
    return HTTPException(404, f"{entity} not found: {identifier}")


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


@router.get("/specs")
def list_specs(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
    return {"specs": video_store.list_specs(limit=limit)}


@router.get("/specs/{spec_id}")
def read_spec(spec_id: str) -> dict[str, Any]:
    spec = video_store.get_spec(spec_id)
    if not spec:
        raise _not_found("video spec", spec_id)
    return spec


@router.get("/plans/{plan_id}")
def read_plan(plan_id: str) -> dict[str, Any]:
    plan = video_store.get_shot_plan(plan_id)
    if not plan:
        raise _not_found("shot plan", plan_id)
    return plan


@router.get("/jobs")
def list_render_jobs(
    shot_plan_id: str | None = None,
    status: str | None = None,
    renderer: str | None = None,
) -> dict[str, Any]:
    return {
        "jobs": video_store.list_jobs(
            shot_plan_id=shot_plan_id, status=status, renderer=renderer
        )
    }


@router.get("/jobs/{job_id}")
def read_job(job_id: str) -> dict[str, Any]:
    job = video_store.get_job(job_id)
    if not job:
        raise _not_found("render job", job_id)
    return job


@router.get("/queue/stats")
def read_queue_stats() -> dict[str, Any]:
    return video_store.queue_stats()


@router.get("/hunyuan/profile")
def read_hunyuan_profile() -> dict[str, Any]:
    return video_pipeline.hunyuan_profile()


# ---------------------------------------------------------------------------
# Founder-gated writes
# ---------------------------------------------------------------------------


@action_router.post("/specs", dependencies=[Depends(verify_founder_action)])
def create_spec(payload: SpecCreate) -> dict[str, Any]:
    try:
        parsed = video_pipeline.parse_script(payload.script_text, source_name=payload.source_name)
        context = video_pipeline.load_indataflow_context()
        spec_payload = video_pipeline.build_spec(
            parsed,
            project_id=payload.project_id,
            campaign_id=payload.campaign_id,
            aspect_ratio=payload.aspect_ratio,
            fps=payload.fps,
            source_path=None,
            context=context,
        )
        video_pipeline.validate_spec(spec_payload)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    stored = video_store.create_spec(video_pipeline._store_spec_payload(spec_payload))
    video_store.update_spec_status(stored["id"], "planned")
    return {"ok": True, "spec": video_store.get_spec(stored["id"])}


@action_router.post("/plans", dependencies=[Depends(verify_founder_action)])
def create_plan(payload: PlanCreate) -> dict[str, Any]:
    spec = video_store.get_spec(payload.spec_id)
    if not spec:
        raise _not_found("video spec", payload.spec_id)
    visuals = spec.get("beats_visual") or {}
    spec_with_visuals = {**spec, "_beats_visual": visuals}
    try:
        plan_payload, ai_report = video_pipeline.plan_shots(spec_with_visuals)
        video_pipeline.validate_plan(spec, plan_payload)
        video_pipeline.validate_claims(spec, plan_payload)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    plan = video_store.create_shot_plan({
        "video_spec_id": spec["id"],
        "shots": plan_payload["shots"],
        "total_duration_seconds": plan_payload["total_duration_seconds"],
        "status": "planned",
    })
    return {"ok": True, "plan": video_store.get_shot_plan(plan["id"]), "ai": ai_report}


@action_router.post("/plans/{plan_id}/queue", dependencies=[Depends(verify_founder_action)])
def queue_plan(plan_id: str) -> dict[str, Any]:
    try:
        result = video_pipeline.queue_shot_plan(plan_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"ok": True, **result}


@action_router.post("/jobs/{job_id}/retry", dependencies=[Depends(verify_founder_action)])
def retry_render_job(job_id: str) -> dict[str, Any]:
    try:
        job = video_store.retry_job(job_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"ok": True, "job": job}


@action_router.post("/jobs/{job_id}/cancel", dependencies=[Depends(verify_founder_action)])
def cancel_render_job(job_id: str) -> dict[str, Any]:
    try:
        job = video_store.cancel_job(job_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"ok": True, "job": job}


# ---------------------------------------------------------------------------
# Worker lease protocol (dashboard credentials, no founder token)
# ---------------------------------------------------------------------------


@worker_router.get("/render-jobs/next")
def lease_next_render_job(
    worker_id: str = Query(min_length=1, max_length=120),
    renderer: str | None = Query(default=None, max_length=32),
) -> dict[str, Any]:
    try:
        job = video_store.lease_next_job(worker_id, renderer=renderer, lease_seconds=_lease_seconds())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not job:
        return {"ok": True, "job": None}
    return {"ok": True, "job": job}


@worker_router.post("/render-jobs/{job_id}/heartbeat")
def heartbeat_render_job(
    job_id: str, worker_id: str = Query(min_length=1, max_length=120)
) -> dict[str, Any]:
    try:
        job = video_store.heartbeat_job(job_id, worker_id, lease_seconds=_lease_seconds())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"ok": True, "job": job}


@worker_router.post("/render-jobs/{job_id}/complete")
def complete_render_job(
    job_id: str,
    payload: JobComplete,
    worker_id: str = Query(min_length=1, max_length=120),
) -> dict[str, Any]:
    try:
        job = video_store.complete_job(job_id, worker_id, result=payload.result)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"ok": True, "job": job}


@worker_router.post("/render-jobs/{job_id}/fail")
def fail_render_job(
    job_id: str,
    payload: JobFail,
    worker_id: str = Query(min_length=1, max_length=120),
) -> dict[str, Any]:
    try:
        job = video_store.fail_job(
            job_id, worker_id, code=payload.code, message=payload.message, retryable=payload.retryable
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"ok": True, "job": job}
