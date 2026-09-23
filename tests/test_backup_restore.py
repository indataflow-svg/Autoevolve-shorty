import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))


def _run(args: list[str]) -> subprocess.CompletedProcess:
    # Force the same interpreter the test suite runs under (Python 3.12+).
    environ = dict(os.environ, PYTHON=sys.executable)
    return subprocess.run(
        args, capture_output=True, text=True, cwd=REPO, env=environ, timeout=120
    )


def _make_instance(root: Path) -> None:
    (root / "data").mkdir(parents=True)
    (root / "config").mkdir()
    (root / "projects" / "p1").mkdir(parents=True)
    (root / ".env").write_text("DASHBOARD_PASSWORD=secret\n", encoding="utf-8")
    (root / "config" / "logo.svg").write_text("<svg/>", encoding="utf-8")
    (root / "projects" / "p1" / "note.txt").write_text("artifact", encoding="utf-8")

    company = sqlite3.connect(root / "data" / "company.db")
    company.execute("CREATE TABLE sales_leads (id TEXT PRIMARY KEY, email TEXT)")
    company.executemany(
        "INSERT INTO sales_leads VALUES (?, ?)",
        [("l1", "a@example.com"), ("l2", "b@example.com")],
    )
    company.execute("CREATE TABLE marketing_campaigns (id TEXT PRIMARY KEY)")
    company.execute("INSERT INTO marketing_campaigns VALUES ('camp_1')")
    company.commit()
    company.close()

    ops = sqlite3.connect(root / "data" / "company_ops.db")
    ops.execute("CREATE TABLE coding_tasks (id TEXT PRIMARY KEY)")
    ops.execute("INSERT INTO coding_tasks VALUES ('t1')")
    ops.commit()
    ops.close()

    g3 = sqlite3.connect(root / "projects" / "p1" / "g3.sqlite3")
    g3.execute("CREATE TABLE drafts (idempotency_key TEXT PRIMARY KEY)")
    g3.execute("INSERT INTO drafts VALUES ('k1')")
    g3.commit()
    g3.close()


class BackupRestoreTests(unittest.TestCase):
    def _backup(self, root: Path, out: Path) -> Path:
        result = _run(["bash", "scripts/backup.sh", "--root", str(root), "--out", str(out)])
        self.assertEqual(result.returncode, 0, result.stderr)
        archives = sorted(out.glob("*.tar.gz"))
        self.assertEqual(len(archives), 1, archives)
        self.assertTrue(archives[0].with_name(archives[0].name + ".sha256").is_file())
        return archives[0]

    def test_backup_verify_and_restore_verify_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "instance"
            root.mkdir()
            _make_instance(root)
            archive = self._backup(root, Path(tmp) / "backups")

            verify = _run([sys.executable, "scripts/verify_backup.py", "--archive", str(archive)])
            self.assertEqual(verify.returncode, 0, verify.stderr)
            self.assertIn("sales_leads=2", verify.stdout)
            self.assertIn("coding_tasks=1", verify.stdout)

            restore = _run(["bash", "scripts/restore.sh", "--verify", "--archive", str(archive)])
            self.assertEqual(restore.returncode, 0, restore.stderr)
            self.assertIn("archive verifies", restore.stdout)
            self.assertIn("marketing_campaigns=1", restore.stdout)

            # The live instance was never touched by verification.
            self.assertTrue((root / ".env").exists())

    def test_backup_snapshots_databases_instead_of_copying_them(self):
        import backup_lib

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "instance"
            root.mkdir()
            _make_instance(root)
            archive = self._backup(root, Path(tmp) / "backups")

            extract = Path(tmp) / "extracted"
            extract.mkdir()
            backup_lib.extract_archive(archive, extract)
            connection = sqlite3.connect(extract / "data" / "company.db")
            try:
                rows = connection.execute("SELECT COUNT(*) FROM sales_leads").fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(rows, 2)
            # No WAL side files inside the archive: the backup API merged them.
            sidecars = list((extract / "data").glob("*-wal")) + list((extract / "data").glob("*-shm"))
            self.assertEqual(sidecars, [])

    def test_tampered_manifest_fails_verification(self):
        import backup_lib

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "instance"
            root.mkdir()
            _make_instance(root)
            archive = self._backup(root, Path(tmp) / "backups")

            stage = Path(tmp) / "stage"
            stage.mkdir()
            backup_lib.extract_archive(archive, stage)
            manifest = json.loads((stage / backup_lib.MANIFEST_NAME).read_text(encoding="utf-8"))
            for entry in manifest["databases"]:
                if "sales_leads" in entry["tables"]:
                    entry["tables"]["sales_leads"] = 99
            (stage / backup_lib.MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")
            tampered = Path(tmp) / "tampered.tar.gz"
            backup_lib.make_archive(stage, tampered)

            result = _run([sys.executable, "scripts/verify_backup.py", "--archive", str(tampered)])
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("expected 99 rows", result.stderr)

    def test_restore_apply_refuses_a_live_instance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "instance"
            root.mkdir()
            _make_instance(root)
            archive = self._backup(root, Path(tmp) / "backups")
            target = Path(tmp) / "restored"

            sleeper = subprocess.Popen(["sleep", "31337"])
            try:
                result = _run([
                    "bash", "scripts/restore.sh", "--apply", "--archive", str(archive),
                    "--target", str(target), "--live-pattern", "sleep 31337",
                ])
            finally:
                sleeper.kill()
                sleeper.wait()
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("refusing to restore over a live instance", result.stderr)
            self.assertFalse((target / ".env").exists())

            applied = _run([
                "bash", "scripts/restore.sh", "--apply", "--archive", str(archive),
                "--target", str(target), "--live-pattern", "no-such-process-xyz",
            ])
            self.assertEqual(applied.returncode, 0, applied.stdout + applied.stderr)
            self.assertIn("restored", applied.stdout)
            self.assertTrue((target / ".env").is_file())
            self.assertTrue((target / "data" / "company.db").is_file())
            self.assertTrue((target / "projects" / "p1" / "g3.sqlite3").is_file())
            # The manifest describes the archive; it is not part of the instance.
            self.assertFalse((target / "manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
