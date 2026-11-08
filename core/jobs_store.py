"""Small durable job ledger for operations that can outlive one HTTP request.

Cloudflare's edge timeout is shorter than some provider/publisher calls. A
manual post schedule is queued here, the HTTP request returns 202, and the
browser polls a job status endpoint. The job stores only the provider-neutral
result envelope; the post's normal metadata remains the source of truth.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from core.state import connect, now_iso


def init_jobs_db() -> None:
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS publish_jobs (
                id TEXT PRIMARY KEY,
                org_id INTEGER NOT NULL,
                post_id TEXT NOT NULL,
                status TEXT NOT NULL,
                result_json TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(org_id) REFERENCES buffer_orgs(id)
            );
            CREATE INDEX IF NOT EXISTS publish_jobs_org
            ON publish_jobs(org_id, status, created_at DESC);
            """
        )


def create_publish_job(org_id: int, post_id: str) -> dict[str, Any]:
    init_jobs_db()
    timestamp = now_iso()
    job_id = f"pubjob_{uuid.uuid4().hex[:16]}"
    with connect() as db:
        db.execute(
            "INSERT INTO publish_jobs "
            "(id, org_id, post_id, status, created_at, updated_at) "
            "VALUES (?, ?, ?, 'queued', ?, ?)",
            (job_id, int(org_id), post_id, timestamp, timestamp),
        )
    return get_publish_job(job_id, org_id) or {}


def get_publish_job(job_id: str, org_id: int | None = None) -> dict[str, Any] | None:
    init_jobs_db()
    query = "SELECT * FROM publish_jobs WHERE id = ?"
    values: list[Any] = [job_id]
    if org_id is not None:
        query += " AND org_id = ?"
        values.append(int(org_id))
    with connect() as db:
        row = db.execute(query, values).fetchone()
    return _decode(row) if row else None


def latest_publish_job(org_id: int, post_id: str) -> dict[str, Any] | None:
    init_jobs_db()
    with connect() as db:
        row = db.execute(
            "SELECT * FROM publish_jobs WHERE org_id = ? AND post_id = ? "
            "ORDER BY created_at DESC, rowid DESC LIMIT 1",
            (int(org_id), post_id),
        ).fetchone()
    return _decode(row) if row else None


def update_publish_job(
    job_id: str,
    *,
    status: str,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any] | None:
    init_jobs_db()
    with connect() as db:
        db.execute(
            "UPDATE publish_jobs SET status = ?, result_json = ?, error = ?, updated_at = ? "
            "WHERE id = ?",
            (
                status,
                json.dumps(result, ensure_ascii=False) if result is not None else None,
                error,
                now_iso(),
                job_id,
            ),
        )
    return get_publish_job(job_id)


def mark_interrupted_jobs() -> int:
    """A process restart cannot resume an in-flight provider call.
    Keep the record honest instead of leaving it permanently 'running'."""
    init_jobs_db()
    with connect() as db:
        cursor = db.execute(
            "UPDATE publish_jobs SET status = 'unknown', "
            "error = 'process restarted while the provider call was in flight', "
            "updated_at = ? WHERE status IN ('queued', 'running')",
            (now_iso(),),
        )
        return cursor.rowcount


def _decode(row: Any) -> dict[str, Any]:
    value = dict(row)
    if value.get("result_json"):
        try:
            value["result"] = json.loads(value["result_json"])
        except (ValueError, TypeError):
            value["result"] = None
    else:
        value["result"] = None
    value.pop("result_json", None)
    return value
