"""Persistent workflow definitions and execution state.

The workflow layer coordinates the remaining Company Core capabilities;
it does not re-implement any of them. This module owns only the workflow
document, its state machine vocabulary, and durable storage.

Storage follows the ``core.ops_store`` precedent: a small SQLite database with
the full document kept as JSON next to the few fields worth indexing (status,
current_step). The whole document is what the runner loads, persists and
resumes, so one JSON column keeps the schema honest without migrations.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from core.db import open_db


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "workflows.db"

WorkflowStatus = Literal["draft", "ready", "running", "paused", "completed", "failed"]
StepStatus = Literal["completed", "failed", "skipped"]
SuccessMetricType = Literal["engagement", "leads", "qualified_leads", "meetings", "conversion"]

# Every action the workflow engine can run. Kept as data (not an enum) so the
# runner can validate against it and tests can assert the exact surface.
# ``simulate_outreach`` is the only side-effect-free action, used by governance
# to prove a market-validation plan end to end without contacting anyone.
WORKFLOW_ACTIONS = (
    "simulate_outreach",
    "draft_outreach",
    "research_prospects",
    "send_outreach",
)

# Actions that can only ever simulate. Governance may map a plan onto one of
# these; it may never authorize an action that reaches a real system.
SIMULATION_ACTIONS = ("simulate_outreach",)

# Actions that write real artifacts to local state but still reach nothing
# outside the process. A drafted outreach message is an object the founder
# reviews and sends by hand; the step itself cannot contact anyone.
DRAFT_ACTIONS = ("draft_outreach",)

# Actions that only read external systems and write local evidence. Provider
# search costs credits but contacts nobody, so it is governed like a draft:
# capped, attributed, and refused without a ceiling.
READ_ACTIONS = ("research_prospects",)

# Actions that dispatch to the outside world. Reaching an external system is
# authorized only with per-item founder approval plus the production
# idempotency and reconciliation path: send_outreach sends solely drafts the
# founder already approved one by one, through send_approved(). Nothing else
# qualifies, and EXTERNAL_ACTIONS stays empty as the tripwire — anything
# listed there is refused outright.
SEND_ACTIONS = ("send_outreach",)

# Everything governance may authorize. Anything registered but absent from this
# tuple is refused: the runner can execute it, a validation plan cannot.
GOVERNED_ACTIONS: tuple[str, ...] = SIMULATION_ACTIONS + DRAFT_ACTIONS + READ_ACTIONS + SEND_ACTIONS

# Actions that reach a real external system. Deliberately empty until limits
# are enforced when a workflow runs rather than only when a plan is validated;
# anything listed here is refused outright.
EXTERNAL_ACTIONS: tuple[str, ...] = ()

TERMINAL_STATUSES = {"completed", "failed"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str = "wf") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WorkflowTrigger(StrictModel):
    type: Literal["manual", "schedule", "event"] = "manual"
    config: dict[str, Any] = Field(default_factory=dict)


class WorkflowStep(StrictModel):
    id: str
    action: str
    config: dict[str, Any] = Field(default_factory=dict)


class SuccessMetric(StrictModel):
    type: SuccessMetricType = "leads"
    target: float = 0.0


class StepResult(StrictModel):
    """Structured result of one executed step (implementation.md §4)."""

    status: StepStatus
    output: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None
    next_step: str | None = None


class StepExecution(StrictModel):
    """A persisted StepResult plus the observability envelope for it."""

    step_id: str
    action: str
    status: StepStatus
    output: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None
    next_step: str | None = None
    started_at: str
    finished_at: str
    duration_ms: int


class WorkflowEvaluation(StrictModel):
    """The evolution hook (implementation.md §12)."""

    winner: str | None = None
    losers: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""
    next_action: str | None = None


class WorkflowState(StrictModel):
    status: WorkflowStatus = "draft"
    current_step: str | None = None
    results: list[StepExecution] = Field(default_factory=list)
    evaluation: WorkflowEvaluation | None = None
    error: str | None = None


class Workflow(StrictModel):
    id: str
    org_id: int = 0
    name: str
    objective: str = ""
    trigger: WorkflowTrigger = Field(default_factory=WorkflowTrigger)
    steps: list[WorkflowStep] = Field(default_factory=list)
    success_metric: SuccessMetric = Field(default_factory=SuccessMetric)
    state: WorkflowState = Field(default_factory=WorkflowState)
    created_at: str
    updated_at: str


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return open_db(DB_PATH, row_factory=sqlite3.Row)


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS workflows (
                id TEXT PRIMARY KEY,
                org_id INTEGER NOT NULL DEFAULT 0,
                name TEXT NOT NULL,
                objective TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'draft',
                current_step TEXT,
                definition_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(workflows)").fetchall()
        }
        if "org_id" not in columns:
            conn.execute(
                "ALTER TABLE workflows ADD COLUMN org_id INTEGER NOT NULL DEFAULT 0"
            )
            try:
                from core.state import get_active_org

                active = get_active_org()
                if active:
                    conn.execute(
                        "UPDATE workflows SET org_id = ? WHERE org_id = 0",
                        (int(active["id"]),),
                    )
            except Exception:
                pass


def save_workflow(workflow: Workflow) -> Workflow:
    """Persist (insert or replace) a workflow document."""
    init_db()
    workflow = workflow.model_copy(update={"updated_at": now_iso()})
    document = workflow.model_dump(mode="json")
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO workflows (id, org_id, name, objective, status, current_step, definition_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                org_id = excluded.org_id,
                name = excluded.name,
                objective = excluded.objective,
                status = excluded.status,
                current_step = excluded.current_step,
                definition_json = excluded.definition_json,
                updated_at = excluded.updated_at
            """,
            (
                workflow.id,
                workflow.org_id,
                workflow.name,
                workflow.objective,
                workflow.state.status,
                workflow.state.current_step,
                json.dumps(document, ensure_ascii=False),
                workflow.created_at,
                workflow.updated_at,
            ),
        )
    return workflow


def build_workflow(
    *,
    name: str,
    objective: str = "",
    steps: list[dict[str, Any]] | None = None,
    trigger: dict[str, Any] | None = None,
    success_metric: dict[str, Any] | None = None,
    workflow_id: str | None = None,
    org_id: int = 0,
) -> Workflow:
    """Construct (but do not persist) a workflow document; raises ValueError if malformed."""
    timestamp = now_iso()
    return Workflow(
        id=workflow_id or new_id(),
        org_id=int(org_id or 0),
        name=name,
        objective=objective,
        trigger=WorkflowTrigger.model_validate(trigger or {}),
        steps=[WorkflowStep.model_validate(step) for step in (steps or [])],
        success_metric=SuccessMetric.model_validate(success_metric or {}),
        state=WorkflowState(status="draft"),
        created_at=timestamp,
        updated_at=timestamp,
    )


def create_workflow(
    *,
    name: str,
    objective: str = "",
    steps: list[dict[str, Any]] | None = None,
    trigger: dict[str, Any] | None = None,
    success_metric: dict[str, Any] | None = None,
    workflow_id: str | None = None,
    org_id: int = 0,
) -> Workflow:
    workflow = build_workflow(
        name=name, objective=objective, steps=steps, trigger=trigger,
        success_metric=success_metric, workflow_id=workflow_id, org_id=org_id,
    )
    return save_workflow(workflow)


def get_workflow(workflow_id: str) -> Workflow | None:
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT definition_json, org_id FROM workflows WHERE id = ?", (workflow_id,)
        ).fetchone()
    if not row:
        return None
    try:
        workflow = Workflow.model_validate(json.loads(row["definition_json"]))
        return workflow.model_copy(update={"org_id": int(row["org_id"] or 0)})
    except (ValidationError, KeyError, TypeError):
        return None


def list_workflows(
    limit: int = 50, *, status: str | None = None, org_id: int | None = None
) -> list[Workflow]:
    init_db()
    query = "SELECT definition_json, org_id FROM workflows"
    values: list[Any] = []
    filters: list[str] = []
    if status:
        filters.append("status = ?")
        values.append(status)
    if org_id is not None:
        filters.append("org_id = ?")
        values.append(int(org_id))
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY created_at DESC, rowid DESC LIMIT ?"
    values.append(max(1, min(limit, 200)))
    with connect() as conn:
        rows = conn.execute(query, values).fetchall()
    workflows: list[Workflow] = []
    for row in rows:
        try:
            workflow = Workflow.model_validate(json.loads(row["definition_json"]))
            workflows.append(workflow.model_copy(update={"org_id": int(row["org_id"] or 0)}))
        except (ValidationError, KeyError, TypeError):
            continue
    return workflows
