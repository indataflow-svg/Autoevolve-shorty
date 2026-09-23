#!/usr/bin/env python3
"""Restore or verify a company-core backup.

  restore.py --archive PATH --verify
      Extract into a temp dir, assert checksums/schema/row counts, run
      `make doctor` when available (warning only) and print a report.
      Never writes near the live instance.

  restore.py --archive PATH --apply [--target DIR] [--force]
      Merge the archive into a target root. Refuses to run while the target
      looks like a live instance unless --force is given.

Usage: restore.py --archive PATH [--verify | --apply] [--target DIR]
                  [--live-pattern REGEX] [--force]
"""
from __future__ import annotations

import argparse
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

from backup_lib import copy_into_target, extract_archive, report_counts, verify_extracted, workdir  # noqa: E402

DEFAULT_LIVE_PATTERN = r"uvicorn app\.api"


def _live_processes(pattern: str) -> list[int]:
    try:
        result = subprocess.run(
            ["pgrep", "-f", pattern], capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.TimeoutExpired):
        return []  # pgrep missing: cannot detect, do not block
    if result.returncode != 0:
        return []
    # `pgrep -f` also sees this script's own command line (it contains the
    # pattern argument), so exclude our process and its parent: a restore
    # process is never the instance it would overwrite.
    self_pids = {os.getpid(), os.getppid()}
    return [
        pid
        for line in result.stdout.split()
        if line.strip().isdigit()
        and (pid := int(line)) not in self_pids
    ]


def _run_doctor(root: Path) -> str:
    if not shutil.which("make") or not (root / "Makefile").is_file():
        return "doctor: skipped (make not available)"
    result = subprocess.run(["make", "doctor"], cwd=root, capture_output=True, text=True)
    if result.returncode == 0:
        return "doctor: passed"
    tail = (result.stdout + result.stderr).strip().splitlines()[-1:] or ["failed"]
    return f"doctor: warnings ({tail[0]})"


def _print_report(archive_dir: Path, doctor_line: str) -> None:
    for line in report_counts(archive_dir):
        print(f"  {line}")
    print(f"  {doctor_line}")


def verify(args: argparse.Namespace) -> int:
    staging = workdir("cc-restore-")
    try:
        extract_archive(args.archive, staging)
        problems = verify_extracted(staging)
        if problems:
            print(f"FAILED: {len(problems)} problem(s)", file=sys.stderr)
            for problem in problems:
                print(f"  - {problem}", file=sys.stderr)
            return 1
        print(f"archive verifies: {args.archive}")
        _print_report(staging, _run_doctor(args.root))
        return 0
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def apply(args: argparse.Namespace) -> int:
    live = _live_processes(args.live_pattern)
    if live and not args.force:
        print(
            "refusing to restore over a live instance "
            f"(pattern {args.live_pattern!r} matched pid(s) {live}). "
            "Stop the services, or pass --force if you are certain.",
            file=sys.stderr,
        )
        return 2
    staging = workdir("cc-restore-")
    try:
        extract_archive(args.archive, staging)
        problems = verify_extracted(staging)
        if problems:
            print(f"FAILED: archive does not verify ({len(problems)} problem(s))", file=sys.stderr)
            for problem in problems:
                print(f"  - {problem}", file=sys.stderr)
            return 1
        args.target.mkdir(parents=True, exist_ok=True)
        copied = copy_into_target(staging, args.target)
        print(f"restored {copied} file(s) into {args.target}")
        _print_report(staging, _run_doctor(args.target))
        print("Start the service, verify /health, and inspect one saved lead and campaign.")
        return 0
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--verify", action="store_true", help="check the archive only (default)")
    mode.add_argument("--apply", action="store_true", help="restore into the target root")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--target", type=Path, default=None, help="default: --root")
    parser.add_argument("--live-pattern", default=DEFAULT_LIVE_PATTERN,
                        help="pgrep pattern treated as a running instance")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    if not args.archive.is_file():
        print(f"archive not found: {args.archive}", file=sys.stderr)
        return 1
    if args.target is None:
        args.target = args.root
    if args.apply:
        return apply(args)
    return verify(args)


if __name__ == "__main__":
    raise SystemExit(main())
