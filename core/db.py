"""Shared SQLite connection factory.

Every connection path opens databases the same way: a 30-second busy timeout,
WAL journalling and enforced foreign keys. V2 adds a scheduler process that
writes concurrently with FastAPI, and SQLite permits only one writer at a time
even in WAL mode, so a connection without a busy timeout would fail immediately
with ``SQLITE_BUSY`` instead of waiting its turn.

Notes:

- ``timeout=30`` and ``PRAGMA busy_timeout=30000`` are the same setting
  (Python's connect timeout *is* the SQLite busy timeout). Both are set so bare
  connections and third-party code agree on the behaviour.
- ``foreign_keys`` is per-connection and must run on every connect.
- ``journal_mode=WAL`` is persistent per file and idempotent.

Engines under ``engines/`` keep a byte-identical local copy of this function
(``_open``) because their runtimes are launched independently and must not
depend on ``core`` being importable.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

BUSY_TIMEOUT_SECONDS = 30


def open_db(
    path: str | Path,
    *,
    row_factory: Any = None,
    timeout: float = BUSY_TIMEOUT_SECONDS,
) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=timeout)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute(f"PRAGMA busy_timeout={int(timeout * 1000)}")
    if row_factory is not None:
        connection.row_factory = row_factory
    return connection
