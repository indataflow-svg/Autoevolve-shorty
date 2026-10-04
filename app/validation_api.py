"""Market-validation API: plan generation, then governed execution.

The endpoint chain follows the state machine and stops at a simulated result:

    CompanyContext -> marketing routing -> market_validation
    -> market_validation_v1 prompt -> OmniRoute -> Hermes -> structured plan
    -> governance (validate + limit + approval) -> workflow -> runner -> simulation

Governance decides *whether* execution is allowed; the existing workflow runner
decides *how*. Nothing here sends a message, publishes content, spends money, or
calls an external marketing system: the only action governance may authorize is
the side-effect-free ``simulate_outreach`` step.
"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.sales_api import verify_founder_action
from core.company_context import get_company_context
from core.marketing_routing import stored_route_state
from core.plan_governance import (
    GovernanceRecord,
    latest_governance,
    record_from_decision,
    save_governance,
    validate_plan,
)
from core.validation_plan import (
    ValidationPlanRecord,
    build_plan_record,
    get_latest_validation_plan,
    get_validation_plan,
    save_validation_plan,
)
from core.workflow_store import create_workflow

router = APIRouter(prefix="/company/marketing/validation", tags=["market-validation"])


class WorkflowFromPlan(BaseModel):
    """Optional plan to govern. Defaults to the most recent generated plan."""

    plan_id: str | None = None


class ApprovalPayload(BaseModel):
    approved: bool = True


class SimulationRun(BaseModel):
    """Simulation-only execution request. `targets` are identifiers, never people."""

    targets: list[str] = Field(default_factory=list, max_length=50)


def _routable_context():
    """Return the stored context, or explain why planning is not possible yet."""
    routing = stored_route_state()
    if routing.routing_error:
        # The record exists but this build cannot route its state: say that first.
        raise HTTPException(409, routing.routing_error)
    context = get_company_context()
    if context is None:
        raise HTTPException(409, "no company context is stored; complete onboarding first")
    if routing.next_stage != "market_validation":
        raise HTTPException(
            409,
            f"company is routed to {routing.next_stage or 'no stage'}; "
            "a validation plan is only planned for the market_validation state",
        )
    if context.status != "context_complete":
        # An incomplete context cannot support an honest plan: the model would
        # have to invent the missing customer, problem, or objective.
        raise HTTPException(
            422,
            "company context is incomplete: " + ", ".join(context.missing)
            + ". Finish onboarding before generating a validation plan.",
        )
    return context


@router.post("/plan", response_model=ValidationPlanRecord, dependencies=[Depends(verify_founder_action)])
async def create_validation_plan():
    """Plan the first market-validation experiment. Nothing is executed."""
    context = _routable_context()
    # Imported here so a missing optional dependency cannot break the API import.
    from agents.hermes import HermesError, HermesOutputError, plan_market_validation

    try:
        result = await plan_market_validation(context)
    except HermesOutputError as exc:
        raise HTTPException(
            502, f"Hermes did not return a valid validation plan: {exc}"
        ) from exc
    except HermesError as exc:
        raise HTTPException(502, f"Hermes could not plan this validation: {exc}") from exc
    except RuntimeError as exc:  # model router not configured
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:  # provider or transport failure
        raise HTTPException(
            502, f"market validation failed: {type(exc).__name__}: {exc}"
        ) from exc

    record = build_plan_record(result.plan, result.provenance, result.grounding)
    try:
        return save_validation_plan(record)
    except sqlite3.Error as exc:
        # Never report a plan that is not stored.
        raise HTTPException(500, f"validation plan could not be saved: {exc}") from exc


@router.get("/plan", response_model=ValidationPlanRecord)
def read_validation_plan():
    """The most recent plan, or 404 when none has been generated yet."""
    record = get_latest_validation_plan()
    if record is None:
        raise HTTPException(404, "no validation plan has been generated yet")
    return record


def _stored_plan(plan_id: str | None) -> ValidationPlanRecord:
    record = get_validation_plan(plan_id) if plan_id else get_latest_validation_plan()
    if record is None:
        raise HTTPException(404, "no validation plan has been generated yet")
    return record


def _governed_context():
    """The routable, complete context governance needs to authorize a plan."""
    routing = stored_route_state()
    if routing.routing_error:
        raise HTTPException(409, routing.routing_error)
    context = get_company_context()
    if context is None:
        raise HTTPException(409, "no company context is stored; complete onboarding first")
    if routing.next_stage != "market_validation":
        raise HTTPException(
            409,
            f"company is routed to {routing.next_stage or 'no stage'}; "
            "governance only applies to the market_validation state",
        )
    if context.status != "context_complete":
        raise HTTPException(
            422,
            "company context is incomplete: " + ", ".join(context.missing)
            + ". Finish onboarding before governing a plan.",
        )
    return context


@router.get("/workflow", response_model=GovernanceRecord)
def read_governance():
    """The latest governance decision and the lifecycle it has reached."""
    record = latest_governance()
    if record is None:
        raise HTTPException(404, "no plan has been validated for execution yet")
    return record


@router.post("/workflow", response_model=GovernanceRecord, dependencies=[Depends(verify_founder_action)])
def create_workflow_from_plan(payload: WorkflowFromPlan | None = None):
    """Validate a plan and, only if governance allows it, create the workflow.

    A blocked plan is still persisted with its reasons and creates no workflow,
    so a refusal is auditable rather than a silent no-op.
    """
    from core.workflow_store import WorkflowState

    context = _governed_context()
    plan_record = _stored_plan(payload.plan_id if payload else None)
    decision, _ = validate_plan(plan_record.plan, context, plan_id=plan_record.id)
    record = save_governance(record_from_decision(decision))
    if decision.status == "blocked":
        return record

    steps = [
        {"id": action.step_id, "action": action.action, "config": action.config}
        for action in decision.resolved_actions
    ]
    targets = plan_record.plan.limits.target_events
    workflow = create_workflow(
        name=f"Market validation: {context.company.name or 'company'}",
        objective=plan_record.plan.next_action or context.objective.primary_goal or "",
        steps=steps,
        trigger={
            "type": "manual",
            "config": {
                "plan_id": plan_record.id,
                "governance_id": record.id,
                "validation_plan": plan_record.plan.workflow_template,
                "simulation": True,
            },
        },
        success_metric={"type": "qualified_leads", "target": float(targets or 0)},
    )
    # Governance authorizes; the workflow starts as an unexecuted draft.
    workflow.state = WorkflowState(status="draft")
    return save_governance(record.model_copy(update={"workflow_id": workflow.id}))


@router.post("/workflow/approve", response_model=GovernanceRecord, dependencies=[Depends(verify_founder_action)])
def approve_workflow(payload: ApprovalPayload | None = None):
    """Record the founder's approval. Execution stays locked until this exists."""
    record = latest_governance()
    if record is None:
        raise HTTPException(404, "no plan has been validated for execution yet")
    if record.status == "blocked":
        raise HTTPException(409, "plan is blocked by governance: " + "; ".join(record.reasons))
    if not record.workflow_id:
        raise HTTPException(409, "no workflow has been created for this plan yet")
    if payload is not None and payload.approved is False:
        return save_governance(record.model_copy(update={
            "approved_at": None, "execution": {"outcome": "not_approved"},
        }))
    from core.workflow_store import WorkflowState, get_workflow, save_workflow

    workflow = get_workflow(record.workflow_id)
    if workflow is None:
        raise HTTPException(409, "the created workflow no longer exists")
    if workflow.state.status == "draft":
        workflow.state = WorkflowState(status="ready")
        save_workflow(workflow)
    return save_governance(record.model_copy(update={"approved_at": _now()}))


@router.post("/workflow/run", response_model=GovernanceRecord, dependencies=[Depends(verify_founder_action)])
def run_workflow_from_plan(payload: SimulationRun | None = None):
    """Run the approved workflow through the existing runner.

    The only authorized action is ``simulate_outreach``: it returns a simulated
    result and performs no external side effect.
    """
    from core.workflow_store import get_workflow, save_workflow
    from services.workflow_runner import run_workflow

    record = latest_governance()
    if record is None:
        raise HTTPException(404, "no plan has been validated for execution yet")
    if record.status == "blocked":
        raise HTTPException(409, "plan is blocked by governance: " + "; ".join(record.reasons))
    if record.required_approval and not record.approved_at:
        raise HTTPException(409, "governance requires founder approval before execution")
    if not record.workflow_id:
        raise HTTPException(409, "no workflow has been created for this plan yet")
    workflow = get_workflow(record.workflow_id)
    if workflow is None:
        raise HTTPException(409, "the created workflow no longer exists")
    targets = (payload.targets if payload else []) or []
    if targets:
        # Simulation targets are written into the existing step config; nothing
        # is resolved against a provider.
        for index, step in enumerate(workflow.steps):
            config = {**step.config, "targets": targets}
            workflow.steps[index] = step.model_copy(update={"config": config})
        save_workflow(workflow)
    executed = run_workflow(record.workflow_id)
    execution = {
        "workflow_id": executed.id,
        "status": executed.state.status,
        "current_step": executed.state.current_step,
        "error": executed.state.error,
        "steps": [
            {
                "step_id": item.step_id,
                "action": item.action,
                "status": item.status,
                "output": item.output,
                "error": item.error,
            }
            for item in executed.state.results
        ],
    }
    return save_governance(record.model_copy(update={
        "executed_at": _now(), "execution": execution,
    }))


def _now() -> str:
    from core.state import now_iso

    return now_iso()