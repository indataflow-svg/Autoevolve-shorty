"""Minimal persisted workflow runner (implementation.md §5).

The runner is a linear, resumable state machine over the existing capability
adapters in ``services.workflow_actions``. It validates a workflow, executes
steps in order, persists the result of every step, stops safely on failure and
never repeats a completed step. It deliberately does not implement retries,
distributed locks, scheduling or agent planning.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from core import workflow_store
from core.workflow_store import (
    WORKFLOW_ACTIONS,
    StepExecution,
    StepResult,
    Workflow,
    WorkflowEvaluation,
    now_iso,
)


class WorkflowValidationError(ValueError):
    """Raised when a workflow cannot be executed as defined."""


def validate_workflow(workflow: Workflow) -> list[str]:
    """Return the list of problems that block execution (empty means valid)."""
    issues: list[str] = []
    if not workflow.name.strip():
        issues.append("workflow name must not be empty")
    if not workflow.steps:
        issues.append("workflow must define at least one step")
    seen: set[str] = set()
    for step in workflow.steps:
        if not step.id.strip():
            issues.append("every step requires a non-empty id")
        elif step.id in seen:
            issues.append(f"duplicate step id: {step.id}")
        seen.add(step.id)
        if step.action not in WORKFLOW_ACTIONS:
            issues.append(
                f"unknown action {step.action!r}; expected one of {sorted(WORKFLOW_ACTIONS)}"
            )
    return issues


def _resolve_action(name: str) -> Callable[[dict, dict], Any]:
    """Look the adapter up at call time so tests can substitute at the boundary."""
    from services import workflow_actions

    function = getattr(workflow_actions, name, None)
    if not callable(function):
        raise LookupError(f"workflow action {name!r} is not implemented")
    return function


def _build_context(workflow: Workflow) -> dict[str, Any]:
    context: dict[str, Any] = {
        "workflow_id": workflow.id,
        "objective": workflow.objective,
        "success_metric": workflow.success_metric.model_dump(mode="json"),
    }
    # Run parameters (org_id, topic, platforms, ...) live on the trigger config.
    context.update(workflow.trigger.config)
    for execution in workflow.state.results:
        if execution.status == "completed":
            context.update(execution.output)
    return context


def _normalize_result(raw: Any) -> StepResult:
    if raw is None:
        return StepResult(status="completed")
    if isinstance(raw, StepResult):
        return raw
    if not isinstance(raw, dict):
        raise TypeError(f"workflow action returned {type(raw).__name__}, expected a mapping")
    payload = dict(raw)
    payload.setdefault("status", "completed")
    return StepResult.model_validate(payload)


def _execute_step(step, context: dict[str, Any]) -> StepExecution:
    function = _resolve_action(step.action)
    started_at = now_iso()
    started = time.perf_counter()
    try:
        result = _normalize_result(function(context, dict(step.config)))
    except Exception as exc:  # noqa: BLE001 - a failed step is recorded, not raised
        result = StepResult(status="failed", error=f"{type(exc).__name__}: {exc}")
    finished_at = now_iso()
    return StepExecution(
        step_id=step.id,
        action=step.action,
        status=result.status,
        output=result.output,
        metrics=result.metrics,
        artifacts=result.artifacts,
        error=result.error,
        next_step=result.next_step,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=int((time.perf_counter() - started) * 1000),
    )


def _replace_result(workflow: Workflow, execution: StepExecution) -> None:
    """Keep at most one persisted result per step id (resume overwrites)."""
    retained = [item for item in workflow.state.results if item.step_id != execution.step_id]
    retained.append(execution)
    workflow.state.results = retained


def run_workflow(workflow_id: str, *, resume: bool = False) -> Workflow:
    """Execute a workflow in order, persisting after every step.

    ``resume`` allows a failed or paused workflow to continue from the first
    step without a ``completed`` result. Without it, a terminal workflow is
    returned unchanged so repeated calls never duplicate completed work.
    """
    workflow = workflow_store.get_workflow(workflow_id)
    if workflow is None:
        raise LookupError(f"workflow not found: {workflow_id}")

    status = workflow.state.status
    if status == "completed":
        return workflow
    if status in {"failed", "paused"} and not resume:
        return workflow

    issues = validate_workflow(workflow)
    if issues:
        raise WorkflowValidationError("; ".join(issues))

    workflow.state.status = "running"
    workflow.state.error = None
    workflow = workflow_store.save_workflow(workflow)

    context = _build_context(workflow)
    completed_ids = {
        execution.step_id
        for execution in workflow.state.results
        if execution.status == "completed"
    }

    for step in workflow.steps:
        if step.id in completed_ids:
            continue
        workflow.state.current_step = step.id
        workflow_store.save_workflow(workflow)

        execution = _execute_step(step, context)
        _replace_result(workflow, execution)

        if execution.status == "failed":
            workflow.state.status = "failed"
            workflow.state.current_step = step.id
            workflow.state.error = execution.error or f"step {step.id} failed"
            return workflow_store.save_workflow(workflow)

        completed_ids.add(step.id)
        context.update(execution.output)
        # §12 evolution hook: the evaluator's verdict lives on workflow state.
        if step.action == "evaluate" and isinstance(execution.output.get("evaluation"), dict):
            workflow.state.evaluation = WorkflowEvaluation.model_validate(execution.output["evaluation"])
        workflow = workflow_store.save_workflow(workflow)

    workflow.state.status = "completed"
    workflow.state.current_step = None
    return workflow_store.save_workflow(workflow)


def pause_workflow(workflow_id: str) -> Workflow:
    workflow = workflow_store.get_workflow(workflow_id)
    if workflow is None:
        raise LookupError(f"workflow not found: {workflow_id}")
    if workflow.state.status in {"completed", "failed"}:
        return workflow
    workflow.state.status = "paused"
    return workflow_store.save_workflow(workflow)
