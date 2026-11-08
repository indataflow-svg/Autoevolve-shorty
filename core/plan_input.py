"""One clean, org-scoped input for Hermes and the workflow resolver.

The planner should not read raw tables, and the workflow should not re-derive
what the planner already decided. This module builds the single contract both
consume: confirmed context + a compact evidence digest + the last run + the
limits/allowlists. The hash makes a stored plan reproducible against the exact
input that produced it.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any

from core.company_context import get_company_context, resolve_context_org
from core.evidence import collect_evidence
from core.state import connect

SCHEMA = "company-core.plan-input.v1"


class PlanInputError(RuntimeError):
    """The planner input cannot be built from the recorded company state."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash(payload: dict[str, Any]) -> str:
    body = {key: value for key, value in payload.items() if key != "built_at"}
    return "sha256:" + hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()


def _init_inputs_db() -> None:
    with connect() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS plan_inputs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                org_id INTEGER NOT NULL,
                input_hash TEXT NOT NULL,
                input_json TEXT NOT NULL,
                built_at TEXT NOT NULL,
                UNIQUE(org_id, input_hash)
            )
            """
        )


def _last_run(evidence: dict[str, Any]) -> dict[str, Any]:
    history = evidence.get("history") or []
    if not history:
        return {
            "plan_id": None, "method": None, "channel": None,
            "targets": 0, "sent": 0, "replies": 0, "meetings": 0,
            "observed": False, "observed_count": 0,
            "unknown_reason": "no governed run has been recorded for this org",
            "duration_days": None, "cost_usd": None,
        }
    latest = history[0]
    observed = bool(latest.get("events_observed"))
    return {
        "plan_id": latest.get("plan_id"),
        "governance_id": latest.get("governance_id"),
        "method": latest.get("action"),
        "channel": latest.get("channel"),
        "targets": latest.get("targets") or 0,
        "sent": latest.get("sent") or 0,
        "replies": latest.get("replies") or 0,
        "meetings": latest.get("meetings") or 0,
        "observed": observed,
        "observed_count": latest.get("events_count") or 0,
        "unknown_reason": None if observed else "no validation events were observed for the last run",
        "duration_days": latest.get("duration_days"),
        "executed_at": latest.get("executed_at"),
        "cost_usd": None,
    }


def _constraints(org_id: int = 0) -> dict[str, Any]:
    from core.plan_governance import GovernanceLimits, METHOD_ACTIONS, SUPPORTED_CHANNELS

    limits = GovernanceLimits.load(org_id)
    return {
        "allowed_methods": sorted(METHOD_ACTIONS),
        "allowed_channels": sorted(SUPPORTED_CHANNELS),
        "max_spend_usd": limits.max_spend_usd,
        "max_outreach_contacts": limits.max_outreach_contacts,
        "max_duration_days": limits.max_duration_days,
        "max_actions": limits.max_actions,
        "requires_approval": True,
        # Quotas are enforced by the API; the planner sees the current free
        # ceiling as a hint so it does not propose more than one action.
        "plan_quota": {
            "used": 0,
            "limit": int(os.getenv("FREE_PLAN_PLANS_PER_DAY", "1") or 1),
        },
        "run_quota": {
            "used": 0,
            "limit": int(os.getenv("FREE_PLAN_RUNS_PER_DAY", "1") or 1),
        },
    }


def _benchmarks(context) -> dict[str, Any]:
    try:
        from core.channel_benchmarks import cold_reply_benchmark

        industry = getattr(getattr(context, "customer", None), "industry", None)
        return {"cold_reply": cold_reply_benchmark(industry)}
    except Exception:
        return {}


def build_plan_input(org_id: int | None = None) -> dict[str, Any]:
    """Build the canonical, org-scoped `PlanInput` for today's decision."""
    org = resolve_context_org(org_id)
    context = get_company_context(org)
    if context is None:
        raise PlanInputError("no company context is stored for this org")
    evidence = collect_evidence(org)
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "org_id": org,
        "built_at": _now_iso(),
        "context": {
            **context.model_dump(mode="json"),
            "completeness_percent": context.completeness_percent,
            "missing": list(context.missing or []),
        },
        "evidence": {
            "accounts": evidence.get("accounts") or {},
            "icps": evidence.get("icps") or [],
            "leads": evidence.get("leads") or {},
            "engagement": evidence.get("engagement") or {},
            "channels": evidence.get("channels") or {},
            "history": (evidence.get("history") or [])[:5],
            "world": evidence.get("world") or {},
            "benchmarks": _benchmarks(context),
        },
        "last_run": _last_run(evidence),
        "constraints": _constraints(org),
    }
    payload["input_hash"] = _hash(payload)
    return payload


def save_plan_input(payload: dict[str, Any]) -> dict[str, Any]:
    _init_inputs_db()
    with connect() as db:
        db.execute(
            "INSERT INTO plan_inputs (org_id, input_hash, input_json, built_at) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(org_id, input_hash) DO UPDATE SET "
            "input_json = excluded.input_json",
            (
                int(payload["org_id"]),
                str(payload["input_hash"]),
                _canonical(payload),
                str(payload["built_at"]),
            ),
        )
    return payload


def get_plan_input(org_id: int, input_hash: str) -> dict[str, Any] | None:
    _init_inputs_db()
    with connect() as db:
        row = db.execute(
            "SELECT input_json FROM plan_inputs WHERE org_id=? AND input_hash=?",
            (int(org_id), str(input_hash)),
        ).fetchone()
    if not row:
        return None
    try:
        return json.loads(row["input_json"])
    except (ValueError, TypeError):
        return None
