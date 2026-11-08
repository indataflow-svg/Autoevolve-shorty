"""Per-organization daily quotas and the provider gate.

Free defaults are intentionally small: one plan, one governed run, one real
publish, and no paid provider calls per day. Paid orgs get configurable
defaults. Usage is recorded in `usage_events` so a reset is a date boundary,
not a destructive job.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from core.state import connect, get_org, now_iso

FREE_LIMITS = {"plans": 1, "runs": 1, "publishes": 1}

PAID_DEFAULTS = {
    "plans": 100,
    "runs": 100,
    "publishes": 100,
}


class QuotaExceeded(RuntimeError):
    def __init__(self, kind: str, used: int, limit: int, reset_at: str):
        self.kind = kind
        self.used = used
        self.limit = limit
        self.reset_at = reset_at
        super().__init__(
            f"{kind} quota reached ({used}/{limit}); resets at {reset_at}"
        )


def _init_usage_db() -> None:
    with connect() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS usage_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                org_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                ref TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(org_id, kind, ref)
            )
            """
        )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _day_start(now: datetime | None = None) -> str:
    moment = now or _now()
    return moment.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def reset_at(now: datetime | None = None) -> str:
    moment = now or _now()
    tomorrow = (moment + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return tomorrow.isoformat()


def org_plan(org_id: int | None = None) -> str:
    if org_id is None:
        return "paid"
    org = get_org(int(org_id))
    return str((org or {}).get("plan") or "paid").strip().lower()


def _limit_for(org_id: int | None, kind: str) -> int:
    if kind not in PAID_DEFAULTS:
        raise ValueError(f"unknown quota kind: {kind}")
    plan = org_plan(org_id)
    if plan == "free":
        return FREE_LIMITS[kind]
    env = f"PAID_{kind.upper()}_PER_DAY"
    try:
        return max(0, int(os.getenv(env, str(PAID_DEFAULTS[kind])) or 0))
    except ValueError:
        return PAID_DEFAULTS[kind]


def used_today(org_id: int | None, kind: str) -> int:
    _init_usage_db()
    org = int(org_id or 0)
    with connect() as db:
        row = db.execute(
            "SELECT COUNT(*) FROM usage_events WHERE org_id=? AND kind=? AND created_at>=?",
            (org, kind, _day_start()),
        ).fetchone()
    return int(row[0] or 0)


def quota_snapshot(org_id: int | None, kind: str) -> dict:
    used = used_today(org_id, kind)
    limit = _limit_for(org_id, kind)
    return {
        "kind": kind,
        "plan": org_plan(org_id),
        "used": used,
        "limit": limit,
        "remaining": max(0, limit - used),
        "reset_at": reset_at(),
    }


def enforce_quota(org_id: int | None, kind: str) -> dict:
    snapshot = quota_snapshot(org_id, kind)
    if snapshot["used"] >= snapshot["limit"]:
        raise QuotaExceeded(
            kind, snapshot["used"], snapshot["limit"], snapshot["reset_at"]
        )
    return snapshot


def record_usage(org_id: int | None, kind: str, ref: str) -> None:
    if not ref:
        raise ValueError("usage ref is required")
    _init_usage_db()
    with connect() as db:
        db.execute(
            "INSERT OR IGNORE INTO usage_events (org_id, kind, ref, created_at) "
            "VALUES (?, ?, ?, ?)",
            (int(org_id or 0), kind, str(ref), now_iso()),
        )


def quota_snapshot_all(org_id: int | None) -> dict:
    return {kind: quota_snapshot(org_id, kind) for kind in PAID_DEFAULTS}


def retry_after_seconds(exc: QuotaExceeded) -> int:
    try:
        reset = datetime.fromisoformat(exc.reset_at)
        if reset.tzinfo is None:
            reset = reset.replace(tzinfo=timezone.utc)
        return max(1, int((reset - _now()).total_seconds()))
    except ValueError:
        return 3600


# --- Provider gate ---------------------------------------------------------

def provider_limit(org_id: int | None, provider: str) -> int:
    plan = org_plan(org_id)
    if plan == "free":
        return 0
    key = f"PROVIDER_{str(provider).upper().replace('-', '_')}_DAILY_LIMIT"
    try:
        return max(0, int(os.getenv(key, os.getenv("PROVIDER_DAILY_LIMIT", "100")) or 0))
    except ValueError:
        return 100


def provider_remaining(org_id: int | None, provider: str) -> int:
    from core.state import connect as state_connect

    limit = provider_limit(org_id, provider)
    if limit <= 0:
        return 0
    with state_connect() as db:
        row = db.execute(
            "SELECT COUNT(*) FROM service_provider_requests "
            "WHERE org_id=? AND provider=? AND started_at>=?",
            (
                int(org_id or 0),
                str(provider),
                (_now() - timedelta(hours=24)).isoformat(),
            ),
        ).fetchone()
    return max(0, limit - int(row[0] or 0))


def claim_provider(org_id: int | None, provider: str, action: str) -> bool:
    from core.state import claim_service_provider_request

    return claim_service_provider_request(
        str(provider), str(action), provider_limit(org_id, provider), int(org_id or 0)
    )
