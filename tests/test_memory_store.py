import tempfile
import unittest
from pathlib import Path


class MemoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        import core.state as state

        self.old_path = state.DB_PATH
        state.DB_PATH = Path(self.tmp.name) / "mem.db"
        import core.memory as memory

        memory.init_memory_db()

    def tearDown(self):
        import core.state as state

        state.DB_PATH = self.old_path
        self.tmp.cleanup()

    def test_write_and_recall_same_brand(self):
        import core.memory as memory

        memory.write_memory("indataflow", "lesson", "Stale B/L versions",
                            "Freight teams rebuild status from chat threads", "test")
        hits = memory.recall("indataflow", "freight status chat")
        self.assertTrue(hits)
        self.assertEqual(hits[0]["brand"], "indataflow")

    def test_brand_isolation(self):
        import core.memory as memory

        memory.write_memory("indataflow", "lesson", "Cargo record", "cargo visibility", "t")
        hits = memory.recall("galaxy", "cargo visibility")
        self.assertEqual(hits, [])
        recent = memory.list_recent("galaxy")
        self.assertEqual(recent, [])

    def test_kind_filter_and_counts(self):
        import core.memory as memory

        memory.write_memory("indataflow", "lesson", "A", "alpha text", "t")
        memory.write_memory("indataflow", "win", "B", "beta text", "t")
        self.assertEqual(memory.recall("indataflow", "alpha", kind="lesson")[0]["kind"], "lesson")
        counts = memory.count_by_brand("indataflow")
        self.assertEqual(counts, {"lesson": 1, "win": 1})

    def test_invalid_brand_rejected(self):
        import core.memory as memory

        with self.assertRaises(ValueError):
            memory.write_memory("", "lesson", "t", "x")
        with self.assertRaises(ValueError):
            memory.recall("UPPER SPACE", "x")

    def test_embeddings_never_leaked(self):
        import core.memory as memory

        row = memory.write_memory("indataflow", "lesson", "T", "some text", "t")
        self.assertNotIn("embedding", row)
