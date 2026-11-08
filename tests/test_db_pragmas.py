"""SQLite concurrency settings shared by every connection path.

WAL plus ``synchronous=NORMAL`` is the pairing SQLite recommends for
concurrent readers with a single writer: commits survive a process crash, and
an OS/power loss can only drop the newest transaction, never corrupt the file.
``FULL`` (the previous default) fsyncs the WAL on every commit and buys no
additional safety under WAL.
"""
from __future__ import annotations

from core.db import BUSY_TIMEOUT_SECONDS, open_db


def test_open_db_sets_wal_normal_sync_and_busy_timeout(tmp_path):
    connection = open_db(tmp_path / "company.db")
    try:
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
        synchronous = connection.execute("PRAGMA synchronous").fetchone()[0]
        busy_timeout = connection.execute("PRAGMA busy_timeout").fetchone()[0]
        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
    finally:
        connection.close()

    assert journal_mode == "wal"
    assert synchronous == 1  # NORMAL
    assert busy_timeout == int(BUSY_TIMEOUT_SECONDS * 1000)
    assert foreign_keys == 1


def test_open_db_keeps_row_factory_when_requested(tmp_path):
    def as_dict(cursor, row):
        return {column[0]: value for column, value in zip(cursor.description, row)}

    connection = open_db(tmp_path / "company.db", row_factory=as_dict)
    try:
        connection.execute("CREATE TABLE t (a INTEGER)")
        connection.execute("INSERT INTO t VALUES (1)")
        assert connection.execute("SELECT a FROM t").fetchone() == {"a": 1}
    finally:
        connection.close()
