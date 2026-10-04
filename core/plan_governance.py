"""Deterministic governance between a validation plan and a runnable workflow.

The boundary this module owns (implementation.md §13):

    Hermes decides *what* should happen.
    Governance decides *whether* it is allowed.
    The workflow engine decides *how* it happens.

Nothing in here executes anything and nothing here talks to a model. It reads a
stored :class:`~core.validation_plan.ValidationPlan`, re-checks it against the
founder's CompanyContext and a small set of configured caps, and returns a
structured decision: ``valid`` with the exact workflow actions to create, or
``blocked`` with the reasons why. Callers must persist the decision either way,
so a refusal is auditable rather than silent.

Defaults are deliberately conservative: zero spend, one action, and explicit
founder approval. Every cap is overridable by environment variable so an operator
can loosen one deliberately instead of editing code.
"""

import json
import os
import re
import sqlite3
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from core.company_context import CompanyContext
from core.state import connect, now_iso
from core.validation_plan import GroundingReport, ValidationPlan, enforce_grounding
from core.workflow_store import SIMULATION_ACTIONS, WORKFLOW_ACTIONS

# Channels the product can govern today. A plan outside this vocabulary is
# blocked rather than coerced into the nearest channel.
SUPPORTED_CHANNELS = (
    "email",
    "linkedin",
    "whatsapp",
    "phone",
    "sms",
    "landing-page",
    "in-person",
    "existing-audience",
    "referral",
    "partner",
)

# Validation methods that map onto a governed, side-effect-free action. Anything
# else is blocked: there is no governed execution path for it yet.
METHOD_ACTIONS: dict[str, tuple[str, str]] = {
    "targeted_outbound": ("simulate_outreach", "outbound outreach to a named audience"),
    "direct_sales": ("simulate_outreach", "direct sales outreach to a named buyer"),
}

_NORMALIZE = re.compile(r"[^a-z0-9]+")


def normalize_channel(value: str | None) -> str:
    """Fold founder wording onto a channel key: 'Email' and 'e-mail' -> 'email'."""
    key = _NORMALIZE.sub("-", str(value or "").casefold()).strip("-")
    return {"e-mail": "email", "email-outreach": "email", "cold-email": "email",
            "linked-in": "linkedin", "phone-call": "phone",
            "landing-page-test": "landing-page"}.get(key, key)


def normalize_method(value: str | None) -> str:
    key = _NORMALIZE.sub("_", str(value or "").casefold()).strip("_")
    return {"targeted_outreach_email": "targeted_outreach",
            "cold_outreach": "targeted_outbound",
            "outbound": "targeted_outbound",
            "direct_sales_email": "direct_sales"}.get(key, key)


class GovernanceLimits(BaseModel):
    """Caps the operator has agreed to. Defaults refuse anything costly."""

    max_spend_usd: float = 0.0
    max_actions: int = 1
    max_outreach_contacts: int = 50
    max_duration_days: int = 30

    @classmethod
    def load(cls) -> "GovernanceLimits":
        return cls(
            max_spend_usd=float(os.getenv("VALIDATION_MAX_SPEND_USD", "0") or 0),
            max_actions=int(os.getenv("VALIDATION_MAX_ACTIONS", "1") or 1),
            max_outreach_contacts=int(os.getenv("VALIDATION_MAX_OUTREACH", "50") or 50),
            max_duration_days=int(os.getenv("VALIDATION_MAX_DURATION_DAYS", "30") or 30),
        )


class ResolvedAction(BaseModel):
    """One workflow step governance is willing to authorize."""

    step_id: str
    action: str
    config: dict[str, Any] = Field(default_factory=dict)
    rationale: str


class GovernanceDecision(BaseModel):
    """The structured result of validating one plan. Always persisted."""

    plan_id: str
    status: Literal["valid", "blocked"]
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    required_approval: bool = True
    resolved_actions: list[ResolvedAction] = Field(default_factory=list)
    grounding: GroundingReport = Field(default_factory=GroundingReport)
    limits: GovernanceLimits = Field(default_factory=GovernanceLimits)


def _context_constraints(context: CompanyContext) -> list[str]:
    declared = []
    for name, values in context.constraints.model_dump().items():
        for value in values or []:
            declared.append(f"{name}: {value}")
    return declared


def validate_plan(
    plan: ValidationPlan | dict[str, Any],
    context: CompanyContext,
    *,
    plan_id: str = "",
    limits: GovernanceLimits | None = None,
) -> tuple[GovernanceDecision, ValidationPlan]:
    """Decide whether a plan may become a workflow. Returns (decision, plan).

    The returned plan is the grounded one: any "fact" that cannot be traced to
    the founder's context is demoted to an assumption before anything is checked,
    so a hallucinated customer or result can never reach a workflow step.
    """
    caps = limits or GovernanceLimits.load()
    reasons: list[str] = []
    warnings: list[str] = []

    if isinstance(plan, ValidationPlan):
        grounded_plan, report = enforce_grounding(plan, context)
    else:
        try:
            grounded_plan, report = enforce_grounding(ValidationPlan.model_validate(plan), context)
        except ValueError as exc:
            blocked = GovernanceDecision(
                plan_id=plan_id, status="blocked", limits=caps,
                reasons=[f"plan structure is not a valid validation plan: {exc}"],
            )
            return blocked, ValidationPlan.model_construct()
    if report.moved_to_assumptions:
        warnings.append(
            "untraceable claimed facts were moved to assumptions: "
            + "; ".join(report.moved_to_assumptions)
        )

    # 1. Required content of the experiment itself.
    for label, value in (
        ("target audience", grounded_plan.hypothesis.customer),
        ("problem", grounded_plan.hypothesis.problem),
        ("message", grounded_plan.validation.message),
        ("offer", grounded_plan.validation.offer),
        ("call to action", grounded_plan.validation.call_to_action),
        ("validation event", grounded_plan.validation.validation_event),
        ("success threshold", grounded_plan.validation.success_threshold),
    ):
        if not str(value or "").strip():
            reasons.append(f"plan is missing the {label}")

    # 2. The method must map onto an action this product can actually run.
    method = normalize_method(grounded_plan.validation.method)
    mapping = METHOD_ACTIONS.get(method)
    if not mapping:
        reasons.append(
            f"validation method {grounded_plan.validation.method!r} has no governed workflow action; "
            f"governed methods: {', '.join(sorted(METHOD_ACTIONS))}"
        )
        action_name = ""
    else:
        action_name, rationale = mapping
        if action_name not in WORKFLOW_ACTIONS:
            reasons.append(f"resolved action {action_name!r} is not a registered workflow action")
        elif action_name not in SIMULATION_ACTIONS:
            reasons.append(
                f"action {action_name!r} reaches a real external system and is not authorized by governance"
            )

    # 3. Channel must be supported, and confirmed by the founder when they said.
    channel = normalize_channel(grounded_plan.validation.channel)
    declared_channels = {normalize_channel(item) for item in context.resources.channels or []}
    if channel not in SUPPORTED_CHANNELS:
        reasons.append(
            f"channel {grounded_plan.validation.channel!r} is not a supported validation channel; "
            f"supported: {', '.join(SUPPORTED_CHANNELS)}"
        )
    elif declared_channels:
        if channel not in declared_channels:
            reasons.append(
                f"channel {channel!r} is not among the founder-confirmed channels "
                f"({', '.join(sorted(declared_channels))})"
            )
    else:
        warnings.append(
            f"channel {channel!r} is supported but the founder confirmed no channels yet"
        )

    # 4. Limits: spend, volume, and time must fit inside the operator's caps.
    spend = grounded_plan.limits.max_spend_usd
    if spend is None:
        warnings.append("plan states no spend limit; treated as 0 USD")
    elif spend > caps.max_spend_usd:
        reasons.append(
            f"budget limit: plan allows {spend} USD, governance cap is {caps.max_spend_usd} USD"
        )

    contacts = grounded_plan.limits.max_outreach_contacts
    if contacts is None:
        warnings.append("plan states no outreach volume; treated as 0 contacts")
    elif contacts > caps.max_outreach_contacts:
        reasons.append(
            f"outreach volume limit: plan allows {contacts} contacts, "
            f"governance cap is {caps.max_outreach_contacts}"
        )

    duration = grounded_plan.limits.duration_days
    if duration is None:
        warnings.append("plan states no duration; the workflow is treated as unbounded in time")
    elif duration > caps.max_duration_days:
        reasons.append(
            f"duration limit: plan runs for {duration} days, "
            f"governance cap is {caps.max_duration_days} days"
        )
    if grounded_plan.limits.target_events is None:
        warnings.append(
            "plan states a prose success threshold only; the workflow metric target stays 0"
        )

    if len(METHOD_ACTIONS) and not reasons and grounded_plan.limits.max_outreach_contacts == 0:
        warnings.append("plan authorizes zero contacts, so the workflow would simulate nothing")

    # 5. Approval. Constraints or any spend force it; a plan can never waive it.
    constraints = _context_constraints(context)
    required_approval = True
    if not grounded_plan.limits.requires_approval:
        warnings.append(
            "plan did not request approval; governance still requires founder approval"
        )
    if constraints:
        warnings.append(
            "declared company constraints require founder review before execution: "
            + "; ".join(constraints)
        )

    resolved: list[ResolvedAction] = []
    if not reasons:
        step = ResolvedAction(
            step_id="validate_outreach",
            action=action_name,
            config={
                "channel": channel,
                "message": grounded_plan.validation.message,
                "offer": grounded_plan.validation.offer,
                "call_to_action": grounded_plan.validation.call_to_action,
                "target_audience": grounded_plan.hypothesis.customer,
                "validation_event": grounded_plan.validation.validation_event,
                "max_contacts": int(contacts or 0),
                "duration_days": duration,
            },
            rationale=METHOD_ACTIONS[method][1] if mapping else "",
        )
        resolved = [step]

    decision = GovernanceDecision(
        plan_id=plan_id,
        status="blocked" if reasons else "valid",
        reasons=reasons,
        warnings=warnings,
        required_approval=required_approval,
        resolved_actions=resolved,
        grounding=report,
        limits=caps,
    )
    return decision, grounded_plan


class GovernanceRecord(BaseModel):
    """A persisted governance decision plus the lifecycle it has reached."""

    id: str
    plan_id: str
    status: Literal["valid", "blocked"]
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    required_approval: bool = True
    resolved_actions: list[ResolvedAction] = Field(default_factory=list)
    grounding: GroundingReport = Field(default_factory=GroundingReport)
    limits: GovernanceLimits = Field(default_factory=GovernanceLimits)
    workflow_id: str | None = None
    approved_at: str | None = None
    executed_at: str | None = None
    execution: dict[str, Any] | None = None
    lifecycle: Literal["blocked", "validated", "workflow_created", "approved", "executed"] = "validated"
    created_at: str
    updated_at: str

    @model_validator(mode="after")
    def _derive_lifecycle(self) -> "GovernanceRecord":
        if self.status == "blocked":
            self.lifecycle = "blocked"
        elif self.executed_at:
            self.lifecycle = "executed"
        elif self.approved_at:
            self.lifecycle = "approved"
        elif self.workflow_id:
            self.lifecycle = "workflow_created"
        else:
            self.lifecycle = "validated"
        return self


def new_governance_id() -> str:
    return f"gov_{uuid.uuid4().hex[:12]}"


def record_from_decision(decision: GovernanceDecision, record_id: str | None = None) -> GovernanceRecord:
    timestamp = now_iso()
    return GovernanceRecord(
        id=record_id or new_governance_id(),
        plan_id=decision.plan_id,
        status=decision.status,
        reasons=decision.reasons,
        warnings=decision.warnings,
        required_approval=decision.required_approval,
        resolved_actions=decision.resolved_actions,
        grounding=decision.grounding,
        limits=decision.limits,
        created_at=timestamp,
        updated_at=timestamp,
    )


def init_governance_db() -> None:
    """Create the governance table (idempotent, in the existing company database)."""
    with connect() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS validation_workflows (
                id TEXT PRIMARY KEY,
                plan_id TEXT NOT NULL,
                status TEXT NOT NULL,
                reasons_json TEXT NOT NULL,
                warnings_json TEXT NOT NULL,
                required_approval INTEGER NOT NULL DEFAULT 1,
                resolved_actions_json TEXT NOT NULL,
                grounding_json TEXT NOT NULL,
                limits_json TEXT NOT NULL,
                workflow_id TEXT,
                approved_at TEXT,
                executed_at TEXT,
                execution_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )


def save_governance(record: GovernanceRecord) -> GovernanceRecord:
    init_governance_db()
    document = record.model_dump(mode="json")
    timestamp = now_iso()
    with connect() as db:
        db.execute(
            "INSERT INTO validation_workflows (id, plan_id, status, reasons_json, warnings_json, "
            "required_approval, resolved_actions_json, grounding_json, limits_json, workflow_id, "
            "approved_at, executed_at, execution_json, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET status = excluded.status, "
            "reasons_json = excluded.reasons_json, warnings_json = excluded.warnings_json, "
            "required_approval = excluded.required_approval, "
            "resolved_actions_json = excluded.resolved_actions_json, "
            "grounding_json = excluded.grounding_json, limits_json = excluded.limits_json, "
            "workflow_id = excluded.workflow_id, approved_at = excluded.approved_at, "
            "executed_at = excluded.executed_at, execution_json = excluded.execution_json, "
            "updated_at = excluded.updated_at",
            (
                record.id, record.plan_id, record.status,
                json.dumps(document["reasons"], ensure_ascii=False),
                json.dumps(document["warnings"], ensure_ascii=False),
                1 if record.required_approval else 0,
                json.dumps(document["resolved_actions"], ensure_ascii=False),
                json.dumps(document["grounding"], ensure_ascii=False),
                json.dumps(document["limits"], ensure_ascii=False),
                record.workflow_id, record.approved_at, record.executed_at,
                json.dumps(record.execution, ensure_ascii=False) if record.execution else None,
                record.created_at, timestamp,
            ),
        )
    return record.model_copy(update={"updated_at": timestamp})


def _from_row(row) -> GovernanceRecord:
    document = dict(row)
    return GovernanceRecord.model_validate({
        "id": document["id"],
        "plan_id": document["plan_id"],
        "status": document["status"],
        "reasons": json.loads(document["reasons_json"] or "[]"),
        "warnings": json.loads(document["warnings_json"] or "[]"),
        "required_approval": bool(document["required_approval"]),
        "resolved_actions": json.loads(document["resolved_actions_json"] or "[]"),
        "grounding": json.loads(document["grounding_json"] or "{}"),
        "limits": json.loads(document["limits_json"] or "{}"),
        "workflow_id": document["workflow_id"],
        "approved_at": document["approved_at"],
        "executed_at": document["executed_at"],
        "execution": json.loads(document["execution_json"]) if document["execution_json"] else None,
        "created_at": document["created_at"],
        "updated_at": document["updated_at"],
    })


def get_governance(governance_id: str) -> GovernanceRecord | None:
    init_governance_db()
    with connect() as db:
        row = db.execute(
            "SELECT * FROM validation_workflows WHERE id = ?", (governance_id,)
        ).fetchone()
    if not row:
        return None
    try:
        return _from_row(row)
    except (json.JSONDecodeError, ValueError, sqlite3.DatabaseError):
        return None


def latest_governance() -> GovernanceRecord | None:
    """The most recent decision, so the lifecycle survives a reload."""
    init_governance_db()
    with connect() as db:
        row = db.execute(
            "SELECT * FROM validation_workflows ORDER BY created_at DESC, rowid DESC LIMIT 1"
        ).fetchone()
    if not row:
        return None
    try:
        return _from_row(row)
    except (json.JSONDecodeError, ValueError, sqlite3.DatabaseError):
        return None