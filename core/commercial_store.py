"""Phase 1 commercial foundation: canonical shared model.

Reuses the existing SQLite conventions (core.db.open_db, WAL, single
data/company.db) and the existing sales tables as the source of truth for
leads — this module does not duplicate leads, it adds the commercial layer
around them: offers, ICPs, accounts, opportunities, pipelines, rules,
activities, imports, onboarding sessions, and integration connections.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from core.db import open_db
from core.state import DB_PATH, now_iso


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return open_db(DB_PATH, row_factory=sqlite3.Row)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def active_org_id() -> int:
    try:
        with connect() as db:
            row = db.execute(
                "SELECT value FROM settings WHERE key='active_org_id'"
            ).fetchone()
        return int(row["value"]) if row and str(row["value"]).isdigit() else 0
    except Exception:
        return 0


def init_commercial_db() -> None:
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS offer_profiles (
                id TEXT PRIMARY KEY, org_id INTEGER NOT NULL DEFAULT 0,
                name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT '', target_market TEXT NOT NULL DEFAULT '',
                pricing_model TEXT NOT NULL DEFAULT '', price_info TEXT NOT NULL DEFAULT '',
                value_prop TEXT NOT NULL DEFAULT '', differentiators TEXT NOT NULL DEFAULT '[]',
                limitations TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_offers_org ON offer_profiles(org_id, status);

            CREATE TABLE IF NOT EXISTS icp_profiles (
                id TEXT PRIMARY KEY, org_id INTEGER NOT NULL DEFAULT 0,
                name TEXT NOT NULL, segment TEXT NOT NULL DEFAULT '',
                offer_id TEXT, criteria_json TEXT NOT NULL DEFAULT '[]',
                exclusions_json TEXT NOT NULL DEFAULT '[]',
                weights_json TEXT NOT NULL DEFAULT '{}',
                thresholds_json TEXT NOT NULL DEFAULT '{}',
                provenance_json TEXT NOT NULL DEFAULT '{}',
                evidence_sources_json TEXT NOT NULL DEFAULT '[]',
                assumptions_json TEXT NOT NULL DEFAULT '[]',
                confidence TEXT NOT NULL DEFAULT 'provisional',
                status TEXT NOT NULL DEFAULT 'provisional',
                version INTEGER NOT NULL DEFAULT 1, creator TEXT NOT NULL DEFAULT 'founder',
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_icp_org ON icp_profiles(org_id, status);

            CREATE TABLE IF NOT EXISTS commercial_accounts (
                id TEXT PRIMARY KEY, org_id INTEGER NOT NULL DEFAULT 0,
                company_name TEXT NOT NULL, domain TEXT DEFAULT NULL,
                industry TEXT NOT NULL DEFAULT '', company_size TEXT NOT NULL DEFAULT '',
                region TEXT NOT NULL DEFAULT '', source TEXT NOT NULL DEFAULT 'manual',
                source_ref TEXT NOT NULL DEFAULT '', icp_id TEXT,
                fit_score INTEGER, fit_grade TEXT NOT NULL DEFAULT 'unknown',
                fit_explanation_json TEXT NOT NULL DEFAULT '[]',
                verification_status TEXT NOT NULL DEFAULT 'unverified',
                lifecycle_status TEXT NOT NULL DEFAULT 'target',
                owner TEXT NOT NULL DEFAULT '', next_action TEXT NOT NULL DEFAULT '',
                attributes_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                UNIQUE(org_id, domain)
            );
            CREATE INDEX IF NOT EXISTS idx_acct_org ON commercial_accounts(org_id, lifecycle_status);

            CREATE TABLE IF NOT EXISTS commercial_pipelines (
                id TEXT PRIMARY KEY, org_id INTEGER NOT NULL DEFAULT 0,
                name TEXT NOT NULL, stages_json TEXT NOT NULL DEFAULT '[]',
                active INTEGER NOT NULL DEFAULT 1, version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS commercial_opportunities (
                id TEXT PRIMARY KEY, org_id INTEGER NOT NULL DEFAULT 0,
                account_id TEXT NOT NULL, contact_ids_json TEXT NOT NULL DEFAULT '[]',
                offer_id TEXT, pipeline_id TEXT NOT NULL, stage TEXT NOT NULL,
                stage_history_json TEXT NOT NULL DEFAULT '[]',
                value REAL, currency TEXT NOT NULL DEFAULT 'USD',
                expected_close TEXT, next_action TEXT NOT NULL DEFAULT '',
                outcome TEXT NOT NULL DEFAULT 'open',
                lost_reason TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                FOREIGN KEY(account_id) REFERENCES commercial_accounts(id)
            );
            CREATE INDEX IF NOT EXISTS idx_opp_org ON commercial_opportunities(org_id, stage);

            CREATE TABLE IF NOT EXISTS qualification_rules (
                id TEXT PRIMARY KEY, org_id INTEGER NOT NULL DEFAULT 0,
                name TEXT NOT NULL, icp_id TEXT, pipeline_id TEXT,
                criterion TEXT NOT NULL, rule_type TEXT NOT NULL DEFAULT 'fit',
                weight REAL NOT NULL DEFAULT 1.0, threshold REAL,
                hard_disqualify INTEGER NOT NULL DEFAULT 0,
                evidence_required_json TEXT NOT NULL DEFAULT '[]',
                active INTEGER NOT NULL DEFAULT 1, version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS commercial_activities (
                id TEXT PRIMARY KEY, org_id INTEGER NOT NULL DEFAULT 0,
                type TEXT NOT NULL, timestamp TEXT NOT NULL, outcome TEXT NOT NULL DEFAULT '',
                owner TEXT NOT NULL DEFAULT '', account_id TEXT, contact_id TEXT,
                lead_id TEXT, opportunity_id TEXT, campaign_id TEXT,
                source TEXT NOT NULL DEFAULT 'manual', audit_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_act_org ON commercial_activities(org_id, account_id);

            CREATE TABLE IF NOT EXISTS integration_connections (
                id TEXT PRIMARY KEY, org_id INTEGER NOT NULL DEFAULT 0,
                provider TEXT NOT NULL, external_account_ref TEXT NOT NULL DEFAULT '',
                scopes_json TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'disconnected',
                sync_status TEXT NOT NULL DEFAULT 'idle',
                last_sync_at TEXT, last_error_sanitized TEXT NOT NULL DEFAULT '',
                credential_ref TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                UNIQUE(org_id, provider)
            );

            CREATE TABLE IF NOT EXISTS csv_imports (
                id TEXT PRIMARY KEY, org_id INTEGER NOT NULL DEFAULT 0,
                entity_type TEXT NOT NULL, filename TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'preview',
                mapping_json TEXT NOT NULL DEFAULT '{}',
                totals_json TEXT NOT NULL DEFAULT '{}',
                row_errors_json TEXT NOT NULL DEFAULT '[]',
                rows_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS onboarding_sessions (
                id TEXT PRIMARY KEY, org_id INTEGER NOT NULL DEFAULT 0,
                path TEXT NOT NULL DEFAULT 'A', current_step TEXT NOT NULL DEFAULT 'company',
                progress_json TEXT NOT NULL DEFAULT '{}',
                completed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            """
        )


def _row(table: str, rid: str, org: int) -> dict | None:
    with connect() as db:
        row = db.execute(
            f"SELECT * FROM {table} WHERE id=? AND org_id=?", (rid, org)
        ).fetchone()
    return dict(row) if row else None


def _list(table: str, org: int, limit: int = 100) -> list[dict]:
    with connect() as db:
        rows = db.execute(
            f"SELECT * FROM {table} WHERE org_id=? ORDER BY updated_at DESC LIMIT ?",
            (org, max(1, min(limit, 200))),
        ).fetchall()
    return [dict(r) for r in rows]


# --- deterministic fit evaluation ---
def evaluate_fit(account: dict, icp: dict) -> dict:
    """Score account attributes against ICP criteria. No invented positives."""
    import re

    criteria = json.loads(icp.get("criteria_json") or "[]")
    exclusions = json.loads(icp.get("exclusions_json") or "[]")
    weights = json.loads(icp.get("weights_json") or "{}")
    attrs = {**account, **json.loads(account.get("attributes_json") or "{}")}
    explanations: list[dict] = []
    missing: list[str] = []
    earned = 0.0
    possible = 0.0
    for rule in criteria:
        field = str(rule.get("field") or "")
        op = str(rule.get("operator") or "equals")
        expected = rule.get("value")
        weight = float(weights.get(field, rule.get("weight", 1.0)))
        possible += weight
        actual = attrs.get(field)
        if actual in (None, ""):
            missing.append(field)
            explanations.append({"field": field, "result": "unknown", "reason": "missing evidence"})
            continue
        hit = False
        try:
            a, e = str(actual).lower(), str(expected).lower()
            if op == "equals":
                hit = a == e
            elif op == "contains":
                hit = e in a
            elif op == "in":
                hit = a in [str(x).lower() for x in (expected or [])]
            elif op == "regex":
                hit = bool(re.search(str(expected), str(actual), re.I))
            elif op in ("gte", "lte"):
                hit = (float(actual) >= float(expected)) if op == "gte" else (float(actual) <= float(expected))
        except Exception:
            hit = False
        if hit:
            earned += weight
        explanations.append({"field": field, "result": "match" if hit else "mismatch",
                             "actual": actual, "expected": expected})
    disqualified = False
    for rule in exclusions:
        field, expected = str(rule.get("field") or ""), rule.get("value")
        actual = attrs.get(field)
        if actual is None or actual == "":
            continue
        if str(actual).lower() == str(expected).lower():
            disqualified = True
            explanations.append({"field": field, "result": "disqualified",
                                 "actual": actual, "expected": expected})
    score = int(round(100 * earned / possible)) if possible else 0
    grade = "disqualified" if disqualified else (
        "fit" if score >= 70 else "partial" if score >= 40 else "unfit" if possible else "unknown")
    return {"score": 0 if disqualified else score, "grade": grade,
            "explanations": explanations, "missing": missing,
            "disqualified": disqualified}


def evaluate_intent(org: int, account_id: str) -> dict:
    """Intent from recorded interactions only. Never invents from profile."""
    with connect() as db:
        try:
            lead_rows = db.execute(
                "SELECT id FROM sales_leads WHERE org_id=? AND (id=? OR company IN "
                "(SELECT company_name FROM commercial_accounts WHERE id=?))",
                (org, account_id, account_id),
            ).fetchall()
            lead_ids = [r["id"] for r in lead_rows]
        except Exception:
            lead_ids = []
        signals: list[dict] = []
        score = 0
        if lead_ids:
            marks = ",".join("?" for _ in lead_ids)
            try:
                evts = db.execute(
                    f"SELECT event, lead_id, created_at FROM sales_events WHERE lead_id IN ({marks})"
                    f" ORDER BY id DESC LIMIT 200", lead_ids).fetchall()
                for e in evts:
                    name = str(e["event"])
                    if name in ("lead.replied",):
                        signals.append({"signal": "reply", "lead_id": e["lead_id"], "at": e["created_at"]})
                        score += 30
                    elif name in ("meeting.scheduled",):
                        signals.append({"signal": "meeting", "lead_id": e["lead_id"], "at": e["created_at"]})
                        score += 50
            except Exception:
                pass
            try:
                acts = db.execute(
                    f"SELECT direction, kind, lead_id FROM sales_interactions WHERE lead_id IN ({marks})"
                    f" ORDER BY id DESC LIMIT 200", lead_ids).fetchall()
                for a in acts:
                    if a["direction"] == "inbound":
                        signals.append({"signal": f"inbound_{a['kind']}", "lead_id": a["lead_id"]})
                        score += 20
            except Exception:
                pass
    return {"score": min(score, 100), "signals": signals,
            "level": "high" if score >= 50 else "medium" if score >= 20 else "none",
            "note": "profile-only; no recorded interaction" if not signals else f"{len(signals)} recorded signal(s)"}


init_commercial_db()
