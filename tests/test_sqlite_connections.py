import sqlite3
import tempfile
import time
import unittest
from pathlib import Path


class SqliteConnectionTests(unittest.TestCase):
    """P0-5: every connection path must be normalized before the scheduler
    becomes a second writer on the same files."""

    def test_open_db_applies_v2_pragmas(self):
        from core.db import open_db

        with tempfile.TemporaryDirectory() as tmp:
            connection = open_db(Path(tmp) / "v2.db")
            try:
                self.assertEqual(connection.execute("PRAGMA journal_mode").fetchone()[0].lower(), "wal")
                self.assertEqual(connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
                self.assertEqual(connection.execute("PRAGMA busy_timeout").fetchone()[0], 30000)
            finally:
                connection.close()

    def test_every_core_store_connection_is_normalized(self):
        from core import marketing_store, ops_store, sales_store, state

        for module in (state, ops_store, sales_store, marketing_store):
            original = module.DB_PATH
            try:
                with tempfile.TemporaryDirectory() as tmp:
                    module.DB_PATH = Path(tmp) / "normalize.db"
                    connection = module.connect()
                    try:
                        self.assertEqual(
                            connection.execute("PRAGMA foreign_keys").fetchone()[0], 1, module.__name__
                        )
                        self.assertEqual(
                            connection.execute("PRAGMA busy_timeout").fetchone()[0], 30000, module.__name__
                        )
                    finally:
                        connection.close()
            finally:
                module.DB_PATH = original

    def test_engine_connections_apply_the_same_pragmas(self):
        try:
            from engines.g1.g1_runtime.store import CampaignStore
            from engines.g3.g3_runtime import ledger as g3_ledger
        except ImportError as exc:  # engines need the repo root on sys.path
            raise unittest.SkipTest(f"engines not importable: {exc}")

        with tempfile.TemporaryDirectory() as tmp:
            store = CampaignStore(Path(tmp) / "g1.db")
            with store.connect() as connection:
                self.assertEqual(connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
                self.assertEqual(connection.execute("PRAGMA busy_timeout").fetchone()[0], 30000)
            ledger_connection = g3_ledger._open(Path(tmp) / "g3.db")
            try:
                self.assertEqual(ledger_connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
                self.assertEqual(ledger_connection.execute("PRAGMA busy_timeout").fetchone()[0], 30000)
            finally:
                ledger_connection.close()

    def test_second_writer_waits_instead_of_failing_immediately(self):
        from core.db import open_db

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "busy.db"
            first = open_db(path)
            second = open_db(path, timeout=0.25)
            try:
                first.execute("CREATE TABLE t (x INTEGER)")
                first.execute("BEGIN IMMEDIATE")
                started = time.monotonic()
                with self.assertRaises(sqlite3.OperationalError) as context:
                    second.execute("INSERT INTO t VALUES (1)")
                elapsed = time.monotonic() - started
                self.assertIn("locked", str(context.exception))
                self.assertGreaterEqual(
                    elapsed, 0.15, "second writer failed immediately instead of honoring busy_timeout"
                )
            finally:
                try:
                    first.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                second.close()
                first.close()


if __name__ == "__main__":
    unittest.main()
