#!/usr/bin/env python3
"""Verify a company-core backup archive without touching any live instance.

Asserts the manifest, file checksums, database schema hashes and row counts,
then prints a short report. Exit code 0 means the archive verifies.

Usage: verify_backup.py --archive PATH
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

if sys.version_info < (3, 12):
    sys.exit(
        "company-core backup scripts require Python 3.12+ "
        f"(found {sys.version.split()[0]}); run via .venv or set PYTHON"
    )

from backup_lib import extract_archive, report_counts, verify_extracted, workdir  # noqa: E402


def verify_archive(archive_path: Path) -> tuple[list[str], list[str]]:
    staging = workdir("cc-verify-")
    try:
        extract_archive(archive_path, staging)
        problems = verify_extracted(staging)
        counts = report_counts(staging) if not problems else []
        return problems, counts
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.archive.is_file():
        print(f"archive not found: {args.archive}", file=sys.stderr)
        return 1
    problems, counts = verify_archive(args.archive)
    for line in counts:
        print(f"  {line}")
    if problems:
        print(f"FAILED: {len(problems)} problem(s)", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print(f"OK: {args.archive} verifies (checksums, schema and row counts match)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
