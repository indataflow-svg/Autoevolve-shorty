#!/usr/bin/env python3
"""Create a verified, online-safe backup of a company-core instance.

Databases are snapshotted with the SQLite backup API (never `cp`), plain files
(.env, config/, projects/ artifacts, g3.env) are copied with database files
excluded, and a manifest records sha256 checksums, schema hashes and row
counts so restore.sh --verify can prove the archive is intact.

Usage: backup.py [--root DIR] [--out DIR]
Environment:
  BACKUP_AGE_RECIPIENT   encrypt the archive with age (recipient id)
  BACKUP_GPG_RECIPIENT   encrypt the archive with gpg (key id)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

if sys.version_info < (3, 12):
    sys.exit(
        "company-core backup scripts require Python 3.12+ "
        f"(found {sys.version.split()[0]}); run via .venv or set PYTHON"
    )

from backup_lib import (  # noqa: E402
    PLAIN_PATTERNS, build_manifest, discover_databases, make_archive,
    sha256_file, sqlite_snapshot, workdir, MANIFEST_NAME,
)
from datetime import datetime, timezone  # noqa: E402

PLAIN_DIRS = ("data", "config", "projects")
PLAIN_FILES = (".env", "engines/g3/config/g3.env")


def make_backup(root: Path, out_dir: Path) -> Path:
    staging = workdir("cc-backup-")
    try:
        ignore = shutil.ignore_patterns(*PLAIN_PATTERNS)
        for rel in PLAIN_DIRS:
            src = root / rel
            if src.is_dir():
                shutil.copytree(src, staging / rel, dirs_exist_ok=True, ignore=ignore)
        for rel in PLAIN_FILES:
            src = root / rel
            if src.is_file():
                dst = staging / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

        db_rels: list[str] = []
        for src in discover_databases(root):
            rel = src.relative_to(root).as_posix()
            sqlite_snapshot(src, staging / rel)
            db_rels.append(rel)
        if not db_rels:
            raise RuntimeError(f"no databases found under {root}")

        manifest = build_manifest(staging, db_rels)
        (staging / MANIFEST_NAME).write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        archive = out_dir / f"company-core-{stamp}.tar.gz"
        make_archive(staging, archive)
        archive.with_name(archive.name + ".sha256").write_text(
            f"{sha256_file(archive)}  {archive.name}\n", encoding="utf-8"
        )
        archive = _maybe_encrypt(archive)
        return archive
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _maybe_encrypt(archive: Path) -> Path:
    age_recipient = os.getenv("BACKUP_AGE_RECIPIENT", "").strip()
    gpg_recipient = os.getenv("BACKUP_GPG_RECIPIENT", "").strip()
    if age_recipient:
        target = archive.with_name(archive.name + ".age")
        subprocess.run(["age", "-r", age_recipient, "-o", str(target), str(archive)], check=True)
        archive.unlink()
        return target
    if gpg_recipient:
        target = archive.with_name(archive.name + ".gpg")
        subprocess.run(
            ["gpg", "--batch", "--yes", "-e", "-r", gpg_recipient, "-o", str(target), str(archive)],
            check=True,
        )
        archive.unlink()
        return target
    return archive


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out", type=Path, default=None, help="default: <root>/backups")
    args = parser.parse_args(argv)
    out_dir = args.out or (args.root / "backups")
    try:
        archive = make_backup(args.root, out_dir)
    except Exception as exc:
        print(f"backup failed: {exc}", file=sys.stderr)
        return 1
    print(f"backup written: {archive}")
    print(f"verify it with: python3 scripts/verify_backup.py --archive {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
