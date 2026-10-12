"""Market-validation API: plan generation, then governed execution.

The endpoint chain follows the state machine and stops at a run:

    CompanyContext -> marketing routing -> market_validation
    -> market_validation_v1 prompt -> OmniRoute -> Hermes -> structured plan
    -> governance (validate + limit + approval) -> workflow -> runner -> run

Governance decides *whether* execution is allowed; the existing workflow runner
decides *how*. Nothing here sends a message, publishes content, spends money, or
calls an external marketing system: governance may authorize
``simulate_outreach`` (rehearses) or ``draft_outreach`` (writes local drafts the
founder sends by hand). Anything that would leave this process is refused by
``EXTERNAL_ACTIONS``, which is empty, and the approved limits are re-checked
when the run happens rather than only when the plan was validated.
"""

import sqlite3
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.sales_api import verify_founder_action
from core.company_context import get_company_context, is_workflow_ready
from core.marketing_routing import stored_route_state
from core.plan_governance import (
    GovernanceLimits,
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

# Canonical automation name. The /marketing/validation routes above stay working
# so existing clients and tests keep passing; new code should use these, which
# live under their own /company/automation root and cannot overlap with the
# workflow engine's /company/workflows/{id} routes.
automation_router = APIRouter(prefix="/company/automation", tags=["automation"])


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
        # Two different blocks wear the same status code: nothing recorded yet,
        # versus a recorded stage this build cannot route. Say which one it is.
        detail = (
            "no starting state is recorded, so the company has no route; "
            "record state.marketing_stage to route it"
            if not routing.marketing_stage
            else (
                f"company is routed to {routing.next_stage}; "
                "a validation plan is only planned for the market_validation state"
            )
        )
        raise HTTPException(409, detail)
    if not context.workflow_ready:
        # Workflow preparation unlocks at 80%: Get Started keeps progress, and
        # the data the founder already set counts. Below that the model would
        # have to invent the missing customer, problem, or objective.
        raise HTTPException(
            422,
            f"company context is {context.completeness_percent}% complete "
            f"(needs 80% for workflow preparation): {', '.join(context.missing)}. "
            "Finish the missing answers in Get Started before generating a validation plan.",
        )
    return context


@router.post("/plan", response_model=ValidationPlanRecord, dependencies=[Depends(verify_founder_action)])
async def create_validation_plan():
    """Plan the first market-validation experiment. Nothing is executed."""
    return await _create_plan()


@automation_router.post("/plan", response_model=ValidationPlanRecord, dependencies=[Depends(verify_founder_action)])
async def create_workflows_validation_plan():
    """Canonical automation name for plan creation. Same behavior as /plan above."""
    return await _create_plan()


async def _create_plan() -> ValidationPlanRecord:
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
    return _read_plan()


@automation_router.get("/evidence")
def read_evidence() -> dict:
    """Everything the business has told or shown us, in one place.

    Read-only and transparent: this is exactly what the account, workflow,
    and campaign suggesters see, so a recommendation can always be traced
    back to the evidence behind it. Unknown slots stay unknown.
    """
    from core.evidence import collect_evidence

    return collect_evidence()


@automation_router.get("/plan", response_model=ValidationPlanRecord)
def read_workflows_validation_plan():
    """Canonical automation name for reading the latest plan."""
    return _read_plan()


def _read_plan() -> ValidationPlanRecord:
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
    """The routable, workflow-ready context governance needs to authorize a plan."""
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
    if not context.workflow_ready:
        raise HTTPException(
            422,
            f"company context is {context.completeness_percent}% complete "
            f"(needs 80% for workflow preparation): {', '.join(context.missing)}. "
            "Finish the missing answers in Get Started before governing a plan.",
        )
    return context


@router.get("/workflow", response_model=GovernanceRecord, deprecated=True)
def read_governance():
    """Legacy name. Prefer GET /company/automation/governance."""
    return _read_governance()


@automation_router.get("/governance", response_model=GovernanceRecord)
def read_workflows_governance():
    """The latest governance decision and the lifecycle it has reached."""
    return _read_governance()


def _read_governance() -> GovernanceRecord:
    record = latest_governance()
    if record is None:
        raise HTTPException(404, "no plan has been validated for execution yet")
    return record


@router.post("/workflow", response_model=GovernanceRecord, dependencies=[Depends(verify_founder_action)], deprecated=True)
def create_workflow_from_plan(payload: WorkflowFromPlan | None = None):
    """Legacy name. Prefer POST /company/automation/governance."""
    return _create_governed_workflow(payload)


@automation_router.post("/governance", response_model=GovernanceRecord, dependencies=[Depends(verify_founder_action)])
def create_workflows_governance(payload: WorkflowFromPlan | None = None):
    """Validate a plan and, only if governance allows it, create the workflow.

    A blocked plan is still persisted with its reasons and creates no workflow,
    so a refusal is auditable rather than a silent no-op.
    """
    return _create_governed_workflow(payload)


def _create_governed_workflow(payload: WorkflowFromPlan | None = None) -> GovernanceRecord:
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


@router.post("/workflow/approve", response_model=GovernanceRecord, dependencies=[Depends(verify_founder_action)], deprecated=True)
def approve_workflow(payload: ApprovalPayload | None = None):
    """Legacy name. Prefer POST /company/automation/governance/approve."""
    return _approve_governance(payload)


@automation_router.post("/governance/approve", response_model=GovernanceRecord, dependencies=[Depends(verify_founder_action)])
def approve_workflows_governance(payload: ApprovalPayload | None = None):
    """Record the founder's approval. Execution stays locked until this exists."""
    return _approve_governance(payload)


def _approve_governance(payload: ApprovalPayload | None = None) -> GovernanceRecord:
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


@router.post("/workflow/run", response_model=GovernanceRecord, dependencies=[Depends(verify_founder_action)], deprecated=True)
def run_workflow_from_plan(payload: SimulationRun | None = None):
    """Legacy name. Prefer POST /company/automation/governance/run."""
    return _run_governance(payload)


@automation_router.post("/governance/run", response_model=GovernanceRecord, dependencies=[Depends(verify_founder_action)])
def run_workflows_governance(payload: SimulationRun | None = None):
    """Run the approved workflow through the existing runner.

    Governance may authorize ``simulate_outreach`` (rehearses, touches nothing)
    or ``draft_outreach`` (writes local drafts the founder sends by hand).
    Neither reaches an external system, and the approved limits are re-checked
    here — a cap tightened after approval still governs this run.
    """
    return _run_governance(payload)


def _runtime_limit_violations(record: GovernanceRecord, targets: list[str]) -> list[str]:
    """Checks only a run can make: the world may have moved since approval.

    Validation-time checks catch a plan that asks for too much. These catch a
    cap tightened afterwards, a window that has elapsed, or a target list larger
    than the volume the founder approved — none of which were answerable when
    the plan was validated.
    """
    limits = _stored_plan(record.plan_id).plan.limits
    caps = GovernanceLimits.load()
    reasons: list[str] = []

    if limits.max_spend_usd is not None and limits.max_spend_usd > caps.max_spend_usd:
        reasons.append(
            f"budget limit {limits.max_spend_usd} USD exceeds the current governance "
            f"cap of {caps.max_spend_usd} USD"
        )
    if (
        limits.max_outreach_contacts is not None
        and limits.max_outreach_contacts > caps.max_outreach_contacts
    ):
        reasons.append(
            f"outreach volume limit {limits.max_outreach_contacts} exceeds the current "
            f"governance cap of {caps.max_outreach_contacts}"
        )
    if limits.duration_days is not None and limits.duration_days > caps.max_duration_days:
        reasons.append(
            f"duration limit {limits.duration_days} days exceeds the current governance "
            f"cap of {caps.max_duration_days} days"
        )

    # The effective ceiling is whichever is tighter: what the plan asked for,
    # or what the operator allows today.
    ceiling = caps.max_outreach_contacts
    if limits.max_outreach_contacts is not None:
        ceiling = min(ceiling, limits.max_outreach_contacts)
    if len(targets) > ceiling:
        reasons.append(
            f"run would contact {len(targets)} prospects, above the approved limit of {ceiling}"
        )

    if limits.duration_days is not None:
        started = _parse_timestamp(record.approved_at or record.created_at)
        if started is not None:
            elapsed = datetime.now(timezone.utc) - started
            if elapsed > timedelta(days=limits.duration_days):
                reasons.append(
                    f"the plan's {limits.duration_days}-day window elapsed: it was "
                    "approved more than that ago, so validate it again before running"
                )
    return reasons


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    # A missing offset is treated as UTC so it can never silently extend a window.
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _run_governance(payload: SimulationRun | None = None) -> GovernanceRecord:
    from core.workflow_store import get_workflow, save_workflow
    from services.workflow_actions import observe_validation_events
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
    violations = _runtime_limit_violations(record, targets)
    if violations:
        # Refused rather than truncated: a run that quietly contacts fewer
        # prospects looks identical to one that hit every contact.
        raise HTTPException(
            422,
            "the approved limits no longer cover this run: " + "; ".join(violations),
        )
    if targets:
        # Simulation targets are written into the existing step config; nothing
        # is resolved against a provider.
        for index, step in enumerate(workflow.steps):
            config = {**step.config, "targets": targets}
            workflow.steps[index] = step.model_copy(update={"config": config})
        save_workflow(workflow)
    executed = run_workflow(record.workflow_id)
    # Measured against real evidence after the run, never derived from it: a
    # workflow that observed nothing reports no score rather than a failing one.
    observation = observe_validation_events(
        plan_id=record.plan_id, workflow_id=executed.id
    )
    execution = {
        "workflow_id": executed.id,
        "status": executed.state.status,
        "current_step": executed.state.current_step,
        "error": executed.state.error,
        "validation_events": observation.model_dump(mode="json"),
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


class AutomationWorkflowView(BaseModel):
    """One governed workflow with its decision, plan link, and engine state.

    Powers the Workflows page showcase: KPIs and scores come from the linked
    workflow's step outputs, the plan link traces back to the Hermes plan.
    """

    governance: GovernanceRecord
    workflow_id: str | None = None
    workflow_status: str | None = None
    workflow: dict | None = None


@automation_router.get("/workflows", response_model=list[AutomationWorkflowView])
def list_automation_workflows(limit: int = 20):
    """All governed workflows, newest first, each with its engine document."""
    from core.plan_governance import init_governance_db
    from core.state import connect
    from core.workflow_store import get_workflow

    init_governance_db()
    with connect() as db:
        rows = db.execute(
            "SELECT id FROM validation_workflows ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (max(1, min(limit, 100)),),
        ).fetchall()
    from core.plan_governance import get_governance

    views = []
    for row in rows:
        record = get_governance(row["id"])
        if record is None:
            continue
        document = None
        status = None
        if record.workflow_id:
            workflow = get_workflow(record.workflow_id)
            if workflow is not None:
                document = workflow.model_dump(mode="json")
                status = workflow.state.status
        views.append(AutomationWorkflowView(
            governance=record, workflow_id=record.workflow_id,
            workflow_status=status, workflow=document,
        ))
    return views


def _now() -> str:
    from core.state import now_iso

    return now_iso()