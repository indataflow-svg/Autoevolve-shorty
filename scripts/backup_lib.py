"""Shared helpers for company-core backup, verify and restore.

A live SQLite database must never be copied with `cp`: WAL frames live in
`-wal`/`-shm` side files and a plain copy of the main file can be torn. Every
database here is copied with sqlite3's online backup API (the same mechanism
as the `sqlite3 .backup` command), which produces a consistent snapshot while
writers keep working.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

FORMAT = "company-core.backup.v1"
MANIFEST_NAME = "manifest.json"
DB_SUFFIXES = {".db", ".sqlite", ".sqlite3"}
DB_SIDECAR_SUFFIXES = {"-wal", "-shm", "-journal"}

# Copied verbatim (excluding database files, which are snapshotted instead).
PLAIN_PATTERNS = ("*.db", "*.sqlite", "*.sqlite3", "*-wal", "*-shm", "*-journal")

# Tables the restore report always calls out when they exist.
REPORT_TABLES = (
    "sales_leads", "sales_drafts", "marketing_campaigns",
    "marketing_manual_posts", "coding_tasks", "incidents",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover_databases(root: Path) -> list[Path]:
    found: list[Path] = []
    for base in (root / "data", root / "projects"):
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file() and path.suffix in DB_SUFFIXES:
                found.append(path)
    return found


def sqlite_snapshot(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(src)
    target = sqlite3.connect(dst)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()


def database_info(path: Path, rel: str) -> dict:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        schema_rows = connection.execute(
            "SELECT name, sql FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        tables = {}
        schema_parts = []
        for name, sql in schema_rows:
            count = connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            tables[name] = count
            schema_parts.append(f"{name}:{sql or ''}")
    finally:
        connection.close()
    schema_sha256 = hashlib.sha256("\n".join(schema_parts).encode("utf-8")).hexdigest()
    return {
        "path": rel,
        "sha256": sha256_file(path),
        "schema_sha256": schema_sha256,
        "tables": tables,
    }


def build_manifest(staging: Path, db_rels: list[str]) -> dict:
    files = []
    for path in sorted(staging.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(staging).as_posix()
        if rel == MANIFEST_NAME or rel in db_rels or _is_database(rel):
            continue
        files.append({"path": rel, "sha256": sha256_file(path), "bytes": path.stat().st_size})
    databases = [
        database_info(staging / rel, rel) for rel in sorted(db_rels)
    ]
    return {
        "format": FORMAT,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "files": files,
        "databases": databases,
    }


def _is_database(rel: str) -> bool:
    return Path(rel).suffix in DB_SUFFIXES


def extract_archive(archive_path: Path, dest: Path) -> None:
    with tarfile.open(archive_path, "r:gz") as tar:
        members = tar.getmembers()
        for member in members:
            if member.name.startswith("/") or ".." in Path(member.name).parts:
                raise RuntimeError(f"unsafe path in archive: {member.name}")
        tar.extractall(dest, members=members, filter="data")


def load_manifest(archive_dir: Path) -> dict:
    manifest_path = archive_dir / MANIFEST_NAME
    if not manifest_path.is_file():
        raise RuntimeError(f"archive has no {MANIFEST_NAME}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format") != FORMAT:
        raise RuntimeError(f"unknown backup format: {manifest.get('format')!r}")
    return manifest


def verify_extracted(archive_dir: Path) -> list[str]:
    """Open the extracted archive and assert schema and row counts.
    Returns a list of problems; empty means the archive verifies."""
    problems: list[str] = []
    try:
        manifest = load_manifest(archive_dir)
    except Exception as exc:
        return [str(exc)]
    for entry in manifest.get("files", []):
        path = archive_dir / entry["path"]
        if not path.is_file():
            problems.append(f"missing file: {entry['path']}")
        elif sha256_file(path) != entry["sha256"]:
            problems.append(f"checksum mismatch: {entry['path']}")
    for entry in manifest.get("databases", []):
        rel = entry["path"]
        path = archive_dir / rel
        if not path.is_file():
            problems.append(f"missing database: {rel}")
            continue
        try:
            info = database_info(path, rel)
        except Exception as exc:
            problems.append(f"unreadable database {rel}: {exc}")
            continue
        if info["sha256"] != entry["sha256"]:
            problems.append(f"database checksum mismatch: {rel}")
        if info["schema_sha256"] != entry["schema_sha256"]:
            problems.append(f"schema changed: {rel}")
        expected = entry.get("tables", {})
        for table, count in expected.items():
            actual = info["tables"].get(table)
            if actual != count:
                problems.append(f"{rel}:{table} expected {count} rows, found {actual}")
        for table in info["tables"]:
            if table not in expected:
                problems.append(f"{rel}:{table} is not in the manifest")
    if not manifest.get("databases"):
        problems.append("manifest contains no databases")
    return problems


def report_counts(archive_dir: Path) -> list[str]:
    """Human-readable row counts for the key tables."""
    lines = []
    manifest = load_manifest(archive_dir)
    for entry in manifest.get("databases", []):
        present = [f"{t}={n}" for t, n in entry["tables"].items() if t in REPORT_TABLES]
        lines.append(f"{entry['path']}: " + (", ".join(present) if present else "no key tables"))
    return lines


def copy_into_target(source: Path, target: Path) -> int:
    """Merge an extracted archive into a target root. Returns file count."""
    count = 0
    for path in sorted(source.rglob("*")):
        rel = path.relative_to(source)
        if rel.as_posix() == MANIFEST_NAME:
            continue
        dest = target / rel
        if path.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
        count += 1
    return count


def make_archive(staging: Path, archive_path: Path) -> None:
    with tarfile.open(archive_path, "w:gz") as tar:
        for path in sorted(staging.rglob("*")):
            tar.add(path, arcname=path.relative_to(staging).as_posix())


def workdir(prefix: str) -> Path:
    return Path(tempfile.mkdtemp(prefix=prefix))
