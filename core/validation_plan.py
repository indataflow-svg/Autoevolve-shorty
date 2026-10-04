"""The market-validation plan: schema, grounding rule, and storage.

This module owns what a plan *is* and how it is stored. It has no model, no
provider, and no execution path: producing a plan is
:mod:`agents.hermes`, and acting on one is a later phase.

Two rules are enforced here rather than trusted to the model:

- the plan is a closed structured object, so nothing downstream parses prose;
- ``evidence.known_facts`` must be traceable to the founder's own context. A
  statement that cannot be traced back to the CompanyContext is by definition an
  assumption, so it is moved there instead of being presented as evidence.
"""

import json
import re
import sqlite3
import uuid
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from core.company_context import SCHEMA_VERSION as CONTEXT_SCHEMA_VERSION, CompanyContext
from core.state import connect, now_iso

WORKFLOW_TEMPLATE = "market_validation_v1"
PLAN_STATUS = "planned"

# A known fact has to be recognisably the founder's own wording. The threshold is
# deliberately forgiving about paraphrase and strict about invention.
GROUNDING_THRESHOLD = 0.6

_TOKEN = re.compile(r"[a-z0-9][a-z0-9'+./-]*")
_STOPWORDS = frozenset(
    """a an and are as at be been but by for from has have how in into is it its of on or
    that the their them then there these they this to was were what when where which who
    will with you your our we us not no than so such can could would should may might must
    do does did done have also more most other some any each about after before during""".split()
)


class CommercialHypothesis(BaseModel):
    """One primary hypothesis, stated as a testable claim."""

    customer: str = Field(min_length=3, max_length=400)
    problem: str = Field(min_length=3, max_length=600)
    trigger: str = Field(min_length=3, max_length=400)
    offer: str = Field(min_length=3, max_length=400)
    reason_to_believe: str = Field(min_length=3, max_length=600)
    desired_action: str = Field(min_length=3, max_length=300)


class MarketView(BaseModel):
    """Who, what problem, why now, and what they do instead."""

    target_customer: str = Field(min_length=3, max_length=400)
    problem: str = Field(min_length=3, max_length=600)
    trigger: str = Field(min_length=3, max_length=400)
    alternatives: str = Field(min_length=3, max_length=600)


class ValidationStrategy(BaseModel):
    """The smallest experiment that can produce the validation event.

    ``method`` is free text on purpose: the candidate list is a set of examples,
    not a menu, so the model may justify a method nobody enumerated.
    """

    method: str = Field(min_length=3, max_length=120)
    channel: str = Field(min_length=3, max_length=300)
    message: str = Field(min_length=3, max_length=1200)
    offer: str = Field(min_length=3, max_length=600)
    call_to_action: str = Field(min_length=3, max_length=300)
    validation_event: str = Field(min_length=3, max_length=400)
    success_threshold: str = Field(min_length=3, max_length=400)
    time_window: str = Field(min_length=3, max_length=200)


class EvidenceLedger(BaseModel):
    """Facts the founder gave, assumptions we made, and what we still need."""

    known_facts: list[str] = Field(default_factory=list, max_length=40)
    assumptions: list[str] = Field(default_factory=list, max_length=40)
    unknowns: list[str] = Field(default_factory=list, max_length=40)

    @model_validator(mode="after")
    def _at_least_one_entry(self) -> "EvidenceLedger":
        if not (self.known_facts or self.assumptions or self.unknowns):
            raise ValueError(
                "evidence must separate known_facts, assumptions, or unknowns; "
                "an empty ledger hides the difference between evidence and inference"
            )
        return self


class PlanLimits(BaseModel):
    """Limits the plan proposes. A later phase enforces them before any action."""

    max_spend_usd: float | None = Field(default=None, ge=0)
    max_outreach_contacts: int | None = Field(default=None, ge=0)
    channel: str | None = Field(default=None, max_length=300)
    duration_days: int | None = Field(default=None, ge=0)
    # The numeric success target behind the prose threshold, so a downstream
    # workflow can carry a real metric instead of re-parsing English.
    target_events: int | None = Field(default=None, ge=0)
    requires_approval: bool = True


class ValidationPlan(BaseModel):
    """The structured output of one market-validation pass. A plan, not a run."""

    workflow_template: Literal["market_validation_v1"] = WORKFLOW_TEMPLATE
    hypothesis: CommercialHypothesis
    market: MarketView
    validation: ValidationStrategy
    evidence: EvidenceLedger
    reasoning: str = Field(min_length=20, max_length=4000)
    next_action: str = Field(min_length=5, max_length=600)
    limits: PlanLimits = Field(default_factory=PlanLimits)


class PlanProvenance(BaseModel):
    """Where the plan came from, so a stored plan is never anonymous."""

    generated_by: str = "hermes"
    prompt_version: str
    prompt_path: str
    context_schema_version: int = CONTEXT_SCHEMA_VERSION
    context_updated_at: str | None = None
    model_route: str
    model_name: str
    model_provider: str


class ValidationPlanRecord(BaseModel):
    """A persisted plan. ``planned`` never implies the experiment happened."""

    id: str
    status: Literal["planned"] = PLAN_STATUS
    plan: ValidationPlan
    provenance: PlanProvenance
    grounding: "GroundingReport" = Field(default_factory=lambda: GroundingReport())
    created_at: str


class GroundingReport(BaseModel):
    """What the grounding rule did, so the demotion is never silent."""

    checked_facts: int = 0
    moved_to_assumptions: list[str] = Field(default_factory=list)


ValidationPlanRecord.model_rebuild()


def _tokens(text: str) -> set[str]:
    return {
        token for token in _TOKEN.findall(text.casefold())
        if len(token) > 1 and token not in _STOPWORDS
    }


def grounding_ratio(statement: str, context_text: str) -> float:
    """Share of a statement's meaningful words that appear in the context."""
    words = _tokens(statement)
    if not words:
        return 0.0
    return len(words & _tokens(context_text)) / len(words)


def is_grounded(statement: str, context_text: str) -> bool:
    """True when a claimed fact is recognisably the founder's own wording."""
    return grounding_ratio(statement, context_text) >= GROUNDING_THRESHOLD


def context_text(context: CompanyContext) -> str:
    """Flatten a context into the text a claim must be traceable to."""
    return json.dumps(context.model_dump(mode="json"), ensure_ascii=False)


def enforce_grounding(plan: ValidationPlan, context: CompanyContext) -> tuple[ValidationPlan, GroundingReport]:
    """Demote untraceable "facts" to assumptions and report exactly what moved.

    A statement that cannot be found in the founder's context is not evidence,
    whatever the model called it. This keeps a plan honest without discarding
    the model's reasoning.
    """
    source = context_text(context)
    untraceable = [
        fact for fact in plan.evidence.known_facts if not is_grounded(fact, source)
    ]
    if not untraceable:
        return plan, GroundingReport(checked_facts=len(plan.evidence.known_facts))
    grounded_plan = plan.model_copy(deep=True)
    grounded_plan.evidence.known_facts = [
        fact for fact in plan.evidence.known_facts if fact not in untraceable
    ]
    grounded_plan.evidence.assumptions = list(grounded_plan.evidence.assumptions) + untraceable
    return grounded_plan, GroundingReport(
        checked_facts=len(plan.evidence.known_facts), moved_to_assumptions=untraceable
    )


def new_plan_id() -> str:
    return f"plan_{uuid.uuid4().hex[:12]}"


def init_validation_db() -> None:
    """Create the plan table (idempotent, in the existing company database)."""
    with connect() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS validation_plans (
                id TEXT PRIMARY KEY,
                workflow_template TEXT NOT NULL,
                prompt_version TEXT NOT NULL,
                context_updated_at TEXT,
                status TEXT NOT NULL,
                plan_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )


def save_validation_plan(record: ValidationPlanRecord) -> ValidationPlanRecord:
    """Persist a planned record and return exactly what was stored."""
    init_validation_db()
    with connect() as db:
        db.execute(
            "INSERT INTO validation_plans (id, workflow_template, prompt_version, "
            "context_updated_at, status, plan_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET plan_json = excluded.plan_json, "
            "status = excluded.status",
            (
                record.id,
                record.plan.workflow_template,
                record.provenance.prompt_version,
                record.provenance.context_updated_at,
                record.status,
                json.dumps(record.model_dump(mode="json"), ensure_ascii=False),
                record.created_at,
            ),
        )
    return record


def build_plan_record(
    plan: ValidationPlan,
    provenance: PlanProvenance,
    grounding: GroundingReport,
) -> ValidationPlanRecord:
    return ValidationPlanRecord(
        id=new_plan_id(), plan=plan, provenance=provenance,
        grounding=grounding, created_at=now_iso(),
    )


def get_validation_plan(plan_id: str) -> ValidationPlanRecord | None:
    init_validation_db()
    with connect() as db:
        row = db.execute(
            "SELECT plan_json FROM validation_plans WHERE id = ?", (plan_id,)
        ).fetchone()
    if not row:
        return None
    try:
        return ValidationPlanRecord.model_validate(json.loads(row["plan_json"]))
    except (json.JSONDecodeError, ValueError):
        return None


def get_latest_validation_plan() -> ValidationPlanRecord | None:
    """The newest plan, so the UI can show the current thinking after a reload."""
    init_validation_db()
    with connect() as db:
        row = db.execute(
            "SELECT plan_json FROM validation_plans ORDER BY created_at DESC, rowid DESC LIMIT 1"
        ).fetchone()
    if not row:
        return None
    try:
        return ValidationPlanRecord.model_validate(json.loads(row["plan_json"]))
    except (json.JSONDecodeError, ValueError, sqlite3.DatabaseError):
        return None