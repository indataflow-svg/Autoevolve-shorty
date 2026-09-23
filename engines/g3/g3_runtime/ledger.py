from __future__ import annotations

import sqlite3
from pathlib import Path


# Byte-identical to core.db.open_db: engines run independently and must not
# depend on `core` being importable. See core/db.py for the rationale.
_BUSY_TIMEOUT_SECONDS = 30


def _open(path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=_BUSY_TIMEOUT_SECONDS)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute(f"PRAGMA busy_timeout={int(_BUSY_TIMEOUT_SECONDS * 1000)}")
    return connection


class Ledger:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with _open(self.path) as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS drafts (
                    idempotency_key TEXT PRIMARY KEY,
                    campaign_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    post_id TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def existing(self, key: str) -> str | None:
        with _open(self.path) as db:
            row = db.execute("SELECT post_id FROM drafts WHERE idempotency_key = ?", (key,)).fetchone()
        return row[0] if row else None

    def record(self, key: str, campaign_id: str, platform: str, post_id: str) -> None:
        with _open(self.path) as db:
            db.execute(
                "INSERT INTO drafts(idempotency_key,campaign_id,platform,post_id) VALUES(?,?,?,?)",
                (key, campaign_id, platform, post_id),
            )

