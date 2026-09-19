"""Long-term memory: per-brand isolated recall over SQLite FTS5.

Retrieval backbone: FTS5 keyword index today; `embedding` column reserved
for OmniRoute embeddings later (cosine in Python, no new services).

Brand isolation is hard: every read/write takes an explicit `brand`
(e.g. indataflow, galaxy, autoevolve). No cross-brand queries exist.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone

from core.state import connect


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_memory_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                brand TEXT NOT NULL,
                kind TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                text TEXT NOT NULL DEFAULT '',
                source_ref TEXT NOT NULL DEFAULT '',
                embedding BLOB,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_memories_brand_kind
                ON memories (brand, kind, created_at DESC);
            """
        )
        _ensure_fts(conn)


def _ensure_fts(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='memories_fts'"
    ).fetchone()
    if row:
        return
    conn.execute(
        "CREATE VIRTUAL TABLE memories_fts USING fts5(title, text, content='memories', content_rowid='id')"
    )
    conn.execute(
        "CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN "
        "INSERT INTO memories_fts(rowid, title, text) VALUES (new.id, new.title, new.text); END"
    )
    conn.execute(
        "CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN "
        "INSERT INTO memories_fts(memories_fts, rowid, title, text) VALUES ('delete', old.id, old.title, old.text); END"
    )
    conn.execute(
        "CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN "
        "INSERT INTO memories_fts(memories_fts, rowid, title, text) VALUES ('delete', old.id, old.title, old.text); "
        "INSERT INTO memories_fts(rowid, title, text) VALUES (new.id, new.title, new.text); END"
    )
    # Backfill rows that predate the FTS table.
    conn.execute(
        "INSERT INTO memories_fts(rowid, title, text) "
        "SELECT id, title, text FROM memories "
        "WHERE id NOT IN (SELECT rowid FROM memories_fts)"
    )


def _require_brand(brand: str) -> str:
    slug = (brand or "").strip().lower()
    if not slug or not re.fullmatch(r"[a-z0-9][a-z0-9\-]{0,60}", slug):
        raise ValueError(f"invalid brand: {brand!r}")
    return slug


def write_memory(
    brand: str,
    kind: str,
    title: str,
    text: str,
    source_ref: str = "",
) -> dict:
    """Persist one memory scoped to a brand. Never writes across brands."""
    slug = _require_brand(brand)
    kind = (kind or "").strip().lower() or "note"
    timestamp = now_iso()
    with connect() as conn:
        _ensure_fts(conn)
        cursor = conn.execute(
            "INSERT INTO memories (brand, kind, title, text, source_ref, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (slug, kind, title.strip(), text.strip(), source_ref.strip(), timestamp, timestamp),
        )
        row = conn.execute("SELECT * FROM memories WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return _public_row(dict(row))


def _public_row(row: dict) -> dict:
    row.pop("embedding", None)
    return row


def _fts_query(user_query: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9_\-]{1,40}", user_query.lower())
    if not tokens:
        return ""
    # Prefix-match each token; quoted to avoid FTS syntax injection.
    return " ".join(f'"{t}"*' for t in tokens[:12])


def recall(brand: str, query: str, kind: str | None = None, limit: int = 5) -> list[dict]:
    """Keyword recall scoped to one brand. Returns rank-ordered memories."""
    slug = _require_brand(brand)
    limit = max(1, min(int(limit or 5), 20))
    match = _fts_query(query)
    with connect() as conn:
        _ensure_fts(conn)
        params: list = [slug]
        kind_filter = ""
        if kind:
            kind_filter = "AND m.kind = ?"
            params.append(kind.strip().lower())
        if match:
            try:
                params.append(match)
                rows = conn.execute(
                    "SELECT m.*, bm25(memories_fts) AS rank FROM memories_fts "
                    "JOIN memories m ON m.id = memories_fts.rowid "
                    "WHERE m.brand = ? " + kind_filter + " AND memories_fts MATCH ? "
                    "ORDER BY rank LIMIT ?",
                    (*params, limit),
                ).fetchall()
                return [_public_row(dict(r)) for r in rows]
            except sqlite3.OperationalError:
                pass
        like = f"%{query.strip()}%"
        rows = conn.execute(
            "SELECT * FROM memories WHERE brand = ? " + kind_filter + " AND (title LIKE ? OR text LIKE ?) "
            "ORDER BY created_at DESC LIMIT ?",
            (*params, like, like, limit),
        ).fetchall()
        return [_public_row(dict(r)) for r in rows]


def list_recent(brand: str, kind: str | None = None, limit: int = 10) -> list[dict]:
    slug = _require_brand(brand)
    limit = max(1, min(int(limit or 10), 50))
    with connect() as conn:
        _ensure_fts(conn)
        if kind:
            rows = conn.execute(
                "SELECT * FROM memories WHERE brand = ? AND kind = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (slug, kind.strip().lower(), limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM memories WHERE brand = ? ORDER BY created_at DESC LIMIT ?",
                (slug, limit),
            ).fetchall()
        return [_public_row(dict(r)) for r in rows]


def count_by_brand(brand: str) -> dict[str, int]:
    slug = _require_brand(brand)
    with connect() as conn:
        _ensure_fts(conn)
        rows = conn.execute(
            "SELECT kind, COUNT(*) AS n FROM memories WHERE brand = ? GROUP BY kind",
            (slug,),
        ).fetchall()
        return {row[0]: row[1] for row in rows}


def brand_for_lead(lead: dict | None) -> str | None:
    """Resolve a lead's brand from its metadata. None when untagged (deferred migration)."""
    if not isinstance(lead, dict):
        return None
    for key in ("brand",):
        value = lead.get(key)
        if isinstance(value, str) and value.strip():
            try:
                return _require_brand(value)
            except ValueError:
                pass
    metadata = lead.get("metadata")
    if isinstance(metadata, dict):
        value = metadata.get("brand")
        if isinstance(value, str) and value.strip():
            try:
                return _require_brand(value)
            except ValueError:
                pass
    return None


def record_outcome(
    brand: str | None,
    kind: str,
    title: str,
    text: str,
    source_ref: str = "",
) -> dict | None:
    """Best-effort memory write. Never raises; returns None when skipped/failed."""
    if not brand:
        return None
    try:
        return write_memory(brand, kind, title, text, source_ref)
    except Exception:
        return None
