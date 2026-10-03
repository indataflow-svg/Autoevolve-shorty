"""SQLite store for the VideoSpec -> ShotPlan -> RenderJob pipeline.

Tables live in the shared company database (``core.state.DB_PATH``) next to
the sales/marketing stores:

- ``video_specs``: one normalized row per prepared script.
- ``video_shot_plans``: one shot plan per spec; shots are a JSON list.
- ``video_render_jobs``: the render queue itself. There is no separate queue
  infrastructure in AutoEvolve, so the queue is a table with lease semantics:
  ``pending -> leased -> running -> completed``, with ``failed``/``cancelled``
  as terminal states and heartbeats extending ``leased_until``. A worker asks
  ``GET /company/video/render-jobs/next`` and the oldest pending job (or an
  expired lease) is atomically assigned to it.

Complex fields (transcript, shots, profiles, results) are stored as JSON text
and decoded on read, mirroring ``core.marketing_store``.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from core.db import open_db
from core.state import DB_PATH, now_iso

RENDERERS = ("hunyuan", "motion_graphics", "ffmpeg", "asset")
JOB_STATUSES = ("pending", "leased", "running", "completed", "failed", "cancelled")

DEFAULT_LEASE_SECONDS = 300
DEFAULT_MAX_ATTEMPTS = 3


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return open_db(DB_PATH, row_factory=sqlite3.Row)


def init_video_db() -> None:
    with connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS video_specs (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                campaign_id TEXT,
                title TEXT NOT NULL,
                brand_json TEXT NOT NULL DEFAULT '{}',
                format_json TEXT NOT NULL DEFAULT '{}',
                audience_json TEXT,
                narrative TEXT,
                transcript_json TEXT NOT NULL DEFAULT '[]',
                beats_visual_json TEXT NOT NULL DEFAULT '{}',
                visual_rules_json TEXT NOT NULL DEFAULT '{}',
                brand_constraints_json TEXT,
                product_boundary TEXT,
                cta TEXT,
                sources_json TEXT NOT NULL DEFAULT '[]',
                source_script_id TEXT,
                source_path TEXT,
                status TEXT NOT NULL DEFAULT 'draft',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS video_shot_plans (
                id TEXT PRIMARY KEY,
                video_spec_id TEXT NOT NULL,
                shots_json TEXT NOT NULL DEFAULT '[]',
                total_duration_seconds REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'draft',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(video_spec_id) REFERENCES video_specs(id)
            );

            CREATE TABLE IF NOT EXISTS video_render_jobs (
                id TEXT PRIMARY KEY,
                video_spec_id TEXT NOT NULL,
                shot_plan_id TEXT NOT NULL,
                shot_id TEXT NOT NULL,
                priority INTEGER NOT NULL DEFAULT 100,
                renderer TEXT NOT NULL,
                model TEXT,
                prompt TEXT,
                negative_prompt TEXT,
                input_assets_json TEXT NOT NULL DEFAULT '[]',
                output_path TEXT NOT NULL UNIQUE,
                resolution TEXT,
                width INTEGER,
                height INTEGER,
                fps INTEGER,
                frames INTEGER,
                steps INTEGER,
                dtype TEXT,
                seed INTEGER,
                continuity_json TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL DEFAULT 3,
                worker_id TEXT,
                leased_until TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                result_json TEXT,
                error_json TEXT,
                FOREIGN KEY(video_spec_id) REFERENCES video_specs(id),
                FOREIGN KEY(shot_plan_id) REFERENCES video_shot_plans(id)
            );

            CREATE INDEX IF NOT EXISTS idx_video_jobs_queue
                ON video_render_jobs(status, priority, created_at);
            """
        )


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _decode_json(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _decode_spec(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    for key, default in (
        ("brand_json", {}),
        ("format_json", {}),
        ("audience_json", None),
        ("transcript_json", []),
        ("beats_visual_json", {}),
        ("visual_rules_json", {}),
        ("brand_constraints_json", None),
        ("sources_json", []),
    ):
        raw = item.pop(key, None)
        item[key.removesuffix("_json")] = _decode_json(raw, default)
    # Camel-case aliases matching the pipeline/VideoSpec shape.
    item["projectId"] = item.get("project_id")
    item["campaignId"] = item.get("campaign_id")
    item["sourceScriptId"] = item.get("source_script_id")
    return item


def _decode_plan(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["shots"] = _decode_json(item.pop("shots_json", None), [])
    return item


def _decode_job(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["input_assets"] = _decode_json(item.pop("input_assets_json", None), [])
    item["continuity"] = _decode_json(item.pop("continuity_json", None), None)
    item["result"] = _decode_json(item.pop("result_json", None), None)
    item["error"] = _decode_json(item.pop("error_json", None), None)
    return item


# ---------------------------------------------------------------------------
# VideoSpec
# ---------------------------------------------------------------------------


def create_spec(payload: dict[str, Any]) -> dict[str, Any]:
    timestamp = now_iso()
    record = {
        "id": payload.get("id") or _new_id("vspec"),
        "project_id": payload["project_id"],
        "campaign_id": payload.get("campaign_id"),
        "title": payload["title"],
        "brand_json": json.dumps(payload.get("brand") or {}),
        "format_json": json.dumps(payload.get("format") or {}),
        "audience_json": json.dumps(payload["audience"]) if payload.get("audience") is not None else None,
        "narrative": payload.get("narrative"),
        "transcript_json": json.dumps(payload.get("transcript") or []),
        "beats_visual_json": json.dumps(payload.get("beats_visual") or {}),
        "visual_rules_json": json.dumps(payload.get("visualRules") or {}),
        "brand_constraints_json": (
            json.dumps(payload["brandConstraints"]) if payload.get("brandConstraints") is not None else None
        ),
        "product_boundary": payload.get("productBoundary"),
        "cta": payload.get("cta"),
        "sources_json": json.dumps(payload.get("sources") or []),
        "source_script_id": payload.get("sourceScriptId"),
        "source_path": payload.get("source_path"),
        "status": payload.get("status") or "draft",
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO video_specs (
                id, project_id, campaign_id, title, brand_json, format_json,
                audience_json, narrative, transcript_json, beats_visual_json, visual_rules_json,
                brand_constraints_json, product_boundary, cta, sources_json,
                source_script_id, source_path, status, created_at, updated_at
            ) VALUES (
                :id, :project_id, :campaign_id, :title, :brand_json, :format_json,
                :audience_json, :narrative, :transcript_json, :beats_visual_json, :visual_rules_json,
                :brand_constraints_json, :product_boundary, :cta, :sources_json,
                :source_script_id, :source_path, :status, :created_at, :updated_at
            )
            """,
            record,
        )
    return get_spec(record["id"])  # type: ignore[return-value]


def get_spec(spec_id: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute("SELECT * FROM video_specs WHERE id = ?", (spec_id,)).fetchone()
    return _decode_spec(row) if row else None


def list_specs(limit: int = 50) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            "SELECT * FROM video_specs ORDER BY created_at DESC LIMIT ?", (max(1, limit),)
        ).fetchall()
    return [_decode_spec(row) for row in rows]


def update_spec_status(spec_id: str, status: str) -> dict[str, Any] | None:
    with connect() as connection:
        connection.execute(
            "UPDATE video_specs SET status = ?, updated_at = ? WHERE id = ?",
            (status, now_iso(), spec_id),
        )
    return get_spec(spec_id)


# ---------------------------------------------------------------------------
# ShotPlan
# ---------------------------------------------------------------------------


def create_shot_plan(payload: dict[str, Any]) -> dict[str, Any]:
    timestamp = now_iso()
    record = {
        "id": payload.get("id") or _new_id("splan"),
        "video_spec_id": payload["video_spec_id"],
        "shots_json": json.dumps(payload.get("shots") or []),
        "total_duration_seconds": payload.get("total_duration_seconds") or 0,
        "status": payload.get("status") or "draft",
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO video_shot_plans (
                id, video_spec_id, shots_json, total_duration_seconds,
                status, created_at, updated_at
            ) VALUES (
                :id, :video_spec_id, :shots_json, :total_duration_seconds,
                :status, :created_at, :updated_at
            )
            """,
            record,
        )
    return get_shot_plan(record["id"])  # type: ignore[return-value]


def get_shot_plan(plan_id: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute("SELECT * FROM video_shot_plans WHERE id = ?", (plan_id,)).fetchone()
    return _decode_plan(row) if row else None


def list_shot_plans(spec_id: str | None = None) -> list[dict[str, Any]]:
    with connect() as connection:
        if spec_id:
            rows = connection.execute(
                "SELECT * FROM video_shot_plans WHERE video_spec_id = ? ORDER BY created_at DESC",
                (spec_id,),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM video_shot_plans ORDER BY created_at DESC LIMIT 50"
            ).fetchall()
    return [_decode_plan(row) for row in rows]


def update_plan_status(plan_id: str, status: str) -> dict[str, Any] | None:
    with connect() as connection:
        connection.execute(
            "UPDATE video_shot_plans SET status = ?, updated_at = ? WHERE id = ?",
            (status, now_iso(), plan_id),
        )
    return get_shot_plan(plan_id)


# ---------------------------------------------------------------------------
# RenderJob queue
# ---------------------------------------------------------------------------


def enqueue_jobs(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Insert render jobs. Output paths must be unique across the queue."""
    timestamp = now_iso()
    records = []
    for item in rows:
        if item.get("renderer") not in RENDERERS:
            raise ValueError(f"unknown renderer: {item.get('renderer')!r}")
        records.append({
            "id": item.get("id") or _new_id("job"),
            "video_spec_id": item["video_spec_id"],
            "shot_plan_id": item["shot_plan_id"],
            "shot_id": item["shot_id"],
            "priority": int(item.get("priority") or 100),
            "renderer": item["renderer"],
            "model": item.get("model"),
            "prompt": item.get("prompt"),
            "negative_prompt": item.get("negativePrompt"),
            "input_assets_json": json.dumps(item.get("inputAssets") or []),
            "output_path": item["output_path"],
            "resolution": item.get("resolution"),
            "width": item.get("width"),
            "height": item.get("height"),
            "fps": item.get("fps"),
            "frames": item.get("frames"),
            "steps": item.get("steps"),
            "dtype": item.get("dtype"),
            "seed": item.get("seed"),
            "continuity_json": json.dumps(item["continuityContext"])
            if item.get("continuityContext") is not None
            else None,
            "status": "pending",
            "attempts": 0,
            "max_attempts": int(item.get("maxAttempts") or DEFAULT_MAX_ATTEMPTS),
            "worker_id": None,
            "leased_until": None,
            "created_at": timestamp,
            "updated_at": timestamp,
            "started_at": None,
            "completed_at": None,
            "result_json": None,
            "error_json": None,
        })
    with connect() as connection:
        try:
            connection.executemany(
                """
                INSERT INTO video_render_jobs (
                    id, video_spec_id, shot_plan_id, shot_id, priority,
                    renderer, model, prompt, negative_prompt, input_assets_json,
                    output_path, resolution, width, height, fps, frames, steps,
                    dtype, seed, continuity_json, status, attempts, max_attempts,
                    worker_id, leased_until, created_at, updated_at, started_at,
                    completed_at, result_json, error_json
                ) VALUES (
                    :id, :video_spec_id, :shot_plan_id, :shot_id, :priority,
                    :renderer, :model, :prompt, :negative_prompt, :input_assets_json,
                    :output_path, :resolution, :width, :height, :fps, :frames, :steps,
                    :dtype, :seed, :continuity_json, :status, :attempts, :max_attempts,
                    :worker_id, :leased_until, :created_at, :updated_at, :started_at,
                    :completed_at, :result_json, :error_json
                )
                """,
                records,
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"render job conflicts with an already queued job: {exc}") from exc
    return [get_job(record["id"]) for record in records]  # type: ignore[misc]


def get_job(job_id: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute("SELECT * FROM video_render_jobs WHERE id = ?", (job_id,)).fetchone()
    return _decode_job(row) if row else None


def list_jobs(
    shot_plan_id: str | None = None,
    status: str | None = None,
    renderer: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    query = "SELECT * FROM video_render_jobs"
    clauses: list[str] = []
    params: list[Any] = []
    if shot_plan_id:
        clauses.append("shot_plan_id = ?")
        params.append(shot_plan_id)
    if status:
        clauses.append("status = ?")
        params.append(status)
    if renderer:
        clauses.append("renderer = ?")
        params.append(renderer)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY priority ASC, created_at ASC LIMIT ?"
    params.append(max(1, limit))
    with connect() as connection:
        rows = connection.execute(query, params).fetchall()
    return [_decode_job(row) for row in rows]


def queue_stats() -> dict[str, Any]:
    with connect() as connection:
        status_rows = connection.execute(
            "SELECT status, COUNT(*) AS n FROM video_render_jobs GROUP BY status"
        ).fetchall()
        renderer_rows = connection.execute(
            "SELECT renderer, COUNT(*) AS n FROM video_render_jobs "
            "WHERE status IN ('pending', 'leased', 'running') GROUP BY renderer"
        ).fetchall()
    return {
        "by_status": {row["status"]: row["n"] for row in status_rows},
        "queued_by_renderer": {row["renderer"]: row["n"] for row in renderer_rows},
    }


def _lease_deadline(lease_seconds: int) -> str:
    from datetime import datetime, timedelta, timezone

    return (datetime.now(timezone.utc) + timedelta(seconds=max(10, lease_seconds))).isoformat()


def lease_next_job(
    worker_id: str,
    renderer: str | None = None,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> dict[str, Any] | None:
    """Atomically lease the oldest pending job (or reclaim an expired lease).

    Each lease counts as an attempt. Jobs that exhausted ``max_attempts`` are
    never leased; they wait for an operator ``retry``.
    """
    if renderer is not None and renderer not in RENDERERS:
        raise ValueError(f"unknown renderer: {renderer!r}")
    timestamp = now_iso()
    deadline = _lease_deadline(lease_seconds)
    with connect() as connection:
        query = (
            "SELECT * FROM video_render_jobs WHERE attempts < max_attempts AND ("
            "status = 'pending' OR (status = 'leased' AND leased_until IS NOT NULL AND leased_until < ?)"
            ")"
        )
        params: list[Any] = [timestamp]
        if renderer:
            query += " AND renderer = ?"
            params.append(renderer)
        query += " ORDER BY priority ASC, created_at ASC LIMIT 1"
        row = connection.execute(query, params).fetchone()
        if not row:
            return None
        job_id = row["id"]
        started_at = row["started_at"] or timestamp
        connection.execute(
            """
            UPDATE video_render_jobs
            SET status = 'leased', worker_id = ?, leased_until = ?,
                attempts = attempts + 1, started_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (worker_id, deadline, started_at, timestamp, job_id),
        )
    return get_job(job_id)


def _owned_job(job_id: str, worker_id: str, states: tuple[str, ...]) -> dict[str, Any]:
    job = get_job(job_id)
    if not job:
        raise ValueError(f"render job not found: {job_id}")
    if job["status"] not in states:
        raise ValueError(f"job {job_id} is {job['status']}, expected one of {list(states)}")
    if job.get("worker_id") != worker_id:
        raise ValueError(f"job {job_id} is leased by another worker")
    return job


def heartbeat_job(
    job_id: str, worker_id: str, lease_seconds: int = DEFAULT_LEASE_SECONDS
) -> dict[str, Any]:
    _owned_job(job_id, worker_id, ("leased", "running"))
    with connect() as connection:
        connection.execute(
            "UPDATE video_render_jobs SET status = 'running', leased_until = ?, updated_at = ? WHERE id = ?",
            (_lease_deadline(lease_seconds), now_iso(), job_id),
        )
    return get_job(job_id)  # type: ignore[return-value]


def complete_job(job_id: str, worker_id: str, result: dict[str, Any] | None = None) -> dict[str, Any]:
    _owned_job(job_id, worker_id, ("leased", "running"))
    with connect() as connection:
        connection.execute(
            """
            UPDATE video_render_jobs
            SET status = 'completed', result_json = ?, completed_at = ?,
                leased_until = NULL, updated_at = ?
            WHERE id = ?
            """,
            (json.dumps(result or {}), now_iso(), now_iso(), job_id),
        )
    return get_job(job_id)  # type: ignore[return-value]


def fail_job(
    job_id: str,
    worker_id: str,
    code: str | None = None,
    message: str = "",
    retryable: bool = True,
) -> dict[str, Any]:
    job = _owned_job(job_id, worker_id, ("leased", "running"))
    error = {"code": code, "message": message, "retryable": bool(retryable)}
    requeue = retryable and job["attempts"] < job["max_attempts"]
    with connect() as connection:
        if requeue:
            connection.execute(
                """
                UPDATE video_render_jobs
                SET status = 'pending', worker_id = NULL, leased_until = NULL,
                    error_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (json.dumps(error), now_iso(), job_id),
            )
        else:
            connection.execute(
                """
                UPDATE video_render_jobs
                SET status = 'failed', error_json = ?, completed_at = ?,
                    leased_until = NULL, updated_at = ?
                WHERE id = ?
                """,
                (json.dumps(error), now_iso(), now_iso(), job_id),
            )
    return get_job(job_id)  # type: ignore[return-value]


def retry_job(job_id: str) -> dict[str, Any]:
    """Operator requeue of a failed or cancelled job with a fresh attempt budget."""
    job = get_job(job_id)
    if not job:
        raise ValueError(f"render job not found: {job_id}")
    if job["status"] not in ("failed", "cancelled"):
        raise ValueError(f"job {job_id} is {job['status']}; only failed/cancelled jobs can be retried")
    with connect() as connection:
        connection.execute(
            """
            UPDATE video_render_jobs
            SET status = 'pending', attempts = 0, worker_id = NULL,
                leased_until = NULL, error_json = NULL, started_at = NULL,
                completed_at = NULL, updated_at = ?
            WHERE id = ?
            """,
            (now_iso(), job_id),
        )
    return get_job(job_id)  # type: ignore[return-value]


def cancel_job(job_id: str) -> dict[str, Any]:
    job = get_job(job_id)
    if not job:
        raise ValueError(f"render job not found: {job_id}")
    if job["status"] in ("completed", "failed", "cancelled"):
        raise ValueError(f"job {job_id} is already {job['status']}")
    with connect() as connection:
        connection.execute(
            "UPDATE video_render_jobs SET status = 'cancelled', leased_until = NULL, updated_at = ? WHERE id = ?",
            (now_iso(), job_id),
        )
    return get_job(job_id)  # type: ignore[return-value]
