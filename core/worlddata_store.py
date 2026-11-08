"""World-data records: free public data cached locally with vintage stamps.

One generic table for every world source (EDGAR, Companies House, Common
Crawl, ...): (source, kind, ref) is the identity, data_json the payload,
vintage the source's own date (filing quarter, crawl id), fetched_at ours.
Freshness and coverage are always answerable; decay rules elsewhere can
re-verify anything older than their window.

Same SQLite conventions as the other stores (core.db.open_db, WAL, single
data/company.db). Never raises on a missing table: absent world data is
unknown evidence, not zero.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from core.db import open_db
from core.state import DB_PATH, now_iso


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return open_db(DB_PATH, row_factory=sqlite3.Row)


def init_worlddata_db() -> None:
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS world_records (
                source TEXT NOT NULL,
                kind TEXT NOT NULL,
                ref TEXT NOT NULL,
                name TEXT NOT NULL DEFAULT '',
                data_json TEXT NOT NULL DEFAULT '{}',
                vintage TEXT NOT NULL DEFAULT '',
                fetched_at TEXT NOT NULL,
                PRIMARY KEY (source, kind, ref)
            );
            CREATE INDEX IF NOT EXISTS idx_world_kind ON world_records(source, kind);
            """
        )


def upsert_record(source: str, kind: str, ref: str, name: str,
                  data: dict[str, Any], vintage: str = "") -> None:
    with connect() as db:
        db.execute(
            "INSERT INTO world_records (source, kind, ref, name, data_json, vintage, fetched_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (source, kind, ref) DO UPDATE SET"
            " name=excluded.name, data_json=excluded.data_json,"
            " vintage=excluded.vintage, fetched_at=excluded.fetched_at",
            (source, kind, ref, name or "", json.dumps(data or {}, ensure_ascii=False),
             vintage or "", now_iso()),
        )


def count_records(source: str | None = None, kind: str | None = None) -> int:
    try:
        with connect() as db:
            if source and kind:
                row = db.execute(
                    "SELECT COUNT(*) FROM world_records WHERE source=? AND kind=?",
                    (source, kind)).fetchone()
            elif source:
                row = db.execute(
                    "SELECT COUNT(*) FROM world_records WHERE source=?", (source,)).fetchone()
            else:
                row = db.execute("SELECT COUNT(*) FROM world_records").fetchone()
            return int(row[0]) if row else 0
    except Exception:
        return 0


def sources_summary() -> dict[str, Any]:
    """Coverage answer for the evidence union: per-source counts + vintages."""
    try:
        with connect() as db:
            rows = db.execute(
                "SELECT source, kind, COUNT(*) AS records,"
                " MIN(vintage) AS min_vintage, MAX(vintage) AS max_vintage,"
                " MAX(fetched_at) AS last_fetched"
                " FROM world_records GROUP BY source, kind"
                " ORDER BY source, kind").fetchall()
    except Exception:
        return {"present": False, "records": 0, "sources": []}
    sources: dict[str, Any] = {}
    total = 0
    for row in rows:
        entry = sources.setdefault(row["source"], {
            "source": row["source"], "records": 0, "kinds": [],
            "vintages": [], "last_fetched": None})
        entry["records"] += row["records"]
        entry["kinds"].append({"kind": row["kind"], "records": row["records"],
                               "min_vintage": row["min_vintage"] or None,
                               "max_vintage": row["max_vintage"] or None})
        for key in ("min_vintage", "max_vintage"):
            if row[key]:
                entry["vintages"].append(row[key])
        if row["last_fetched"] and (entry["last_fetched"] is None or row["last_fetched"] > entry["last_fetched"]):
            entry["last_fetched"] = row["last_fetched"]
        total += row["records"]
    for entry in sources.values():
        vintages = sorted(entry.pop("vintages"))
        entry["min_vintage"] = vintages[0] if vintages else None
        entry["max_vintage"] = vintages[-1] if vintages else None
    return {"present": total > 0, "records": total, "sources": list(sources.values())}


def find_records(source: str, kind: str, limit: int = 50) -> list[dict[str, Any]]:
    try:
        with connect() as db:
            rows = db.execute(
                "SELECT source, kind, ref, name, data_json, vintage, fetched_at"
                " FROM world_records WHERE source=? AND kind=? LIMIT ?",
                (source, kind, max(1, limit))).fetchall()
    except Exception:
        return []
    out = []
    for row in rows:
        item = dict(row)
        try:
            item["data"] = json.loads(item.pop("data_json") or "{}")
        except ValueError:
            item["data"] = {}
        out.append(item)
    return out


def get_record(source: str, kind: str, ref: str) -> dict[str, Any] | None:
    """One world record by identity. None when absent or on any error."""
    try:
        with connect() as db:
            row = db.execute(
                "SELECT source, kind, ref, name, data_json, vintage, fetched_at"
                " FROM world_records WHERE source=? AND kind=? AND ref=?",
                (source, kind, ref)).fetchone()
    except Exception:
        return None
    if row is None:
        return None
    item = dict(row)
    try:
        item["data"] = json.loads(item.pop("data_json") or "{}")
    except ValueError:
        item["data"] = {}
    return item


def clear_source(source: str, kind: str | None = None) -> int:
    with connect() as db:
        if kind:
            cursor = db.execute(
                "DELETE FROM world_records WHERE source=? AND kind=?", (source, kind))
        else:
            cursor = db.execute("DELETE FROM world_records WHERE source=?", (source,))
        return cursor.rowcount or 0
