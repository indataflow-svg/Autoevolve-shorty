"""Workflow control-plane API (implementation.md §13).

Thin transport over ``core.workflow_store`` and ``services.workflow_runner``.
Authentication is applied where the router is mounted in ``app.api``; no
internal provider credentials ever appear in a workflow document.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from core import workflow_store
from core.workflow_store import Workflow, WorkflowState
from services.workflow_runner import WorkflowValidationError, pause_workflow, run_workflow, validate_workflow

router = APIRouter(prefix="/company/workflows", tags=["workflows"])


class WorkflowCreateRequest(BaseModel):
    name: str
    objective: str = ""
    trigger: dict[str, Any] = Field(default_factory=dict)
    steps: list[dict[str, Any]] = Field(default_factory=list)
    success_metric: dict[str, Any] = Field(default_factory=dict)


class WorkflowRunRequest(BaseModel):
    resume: bool = False


@router.post("", response_model=Workflow, status_code=201)
def create_workflow(payload: WorkflowCreateRequest):
    try:
        workflow = workflow_store.build_workflow(
            name=payload.name,
            objective=payload.objective,
            steps=payload.steps,
            trigger=payload.trigger,
            success_metric=payload.success_metric,
        )
    except ValueError as exc:
        raise HTTPException(400, f"invalid workflow: {exc}") from exc
    # Validate before persisting so a rejected definition leaves no row behind.
    issues = validate_workflow(workflow)
    if issues:
        raise HTTPException(400, "invalid workflow: " + "; ".join(issues))
    return workflow_store.save_workflow(workflow)


@router.get("", response_model=list[Workflow])
def list_workflows(
    limit: int = Query(50, ge=1, le=200),
    status: str | None = Query(None),
):
    return workflow_store.list_workflows(limit=limit, status=status)


@router.get("/{workflow_id}", response_model=Workflow)
def get_workflow(workflow_id: str):
    workflow = workflow_store.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(404, "workflow not found")
    return workflow


@router.post("/{workflow_id}/run", response_model=Workflow)
def run(workflow_id: str, payload: WorkflowRunRequest | None = None):
    try:
        return run_workflow(workflow_id, resume=bool(payload and payload.resume))
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except WorkflowValidationError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/{workflow_id}/pause", response_model=Workflow)
def pause(workflow_id: str):
    try:
        return pause_workflow(workflow_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/{workflow_id}/state", response_model=WorkflowState)
def get_state(workflow_id: str):
    workflow = workflow_store.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(404, "workflow not found")
    return workflow.state
