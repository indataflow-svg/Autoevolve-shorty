#!/usr/bin/env python3
"""Create the empty schema for a fresh AutoEvolve installation.

This is intentionally data-free: no organizations, users, forms, demo leads,
or world records are inserted. The first website signup creates the first org.

Usage:
    .venv/bin/python scripts/bootstrap_db.py
    .venv/bin/python scripts/bootstrap_db.py --check
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def init_schema() -> None:
    from core.bootstrap import init_all_schema

    init_all_schema()


def report() -> bool:
    from core.state import connect

    with connect() as db:
        tables = [
            row["name"]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        ]
        counts = {}
        for table in tables:
            counts[table] = db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        fk_errors = db.execute("PRAGMA foreign_key_check").fetchall()
    print(f"tables: {len(tables)}")
    print(f"integrity: {integrity}")
    print(f"foreign_key_errors: {len(fk_errors)}")
    populated = {name: count for name, count in counts.items() if count}
    if populated:
        print("non-empty tables:")
        for name, count in sorted(populated.items()):
            print(f"  {name}: {count}")
    return integrity == "ok" and not fk_errors and not populated


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="verify an existing DB is empty")
    args = parser.parse_args()
    if not args.check:
        init_schema()
    ok = report()
    if args.check and not ok:
        print("database is not a fresh, empty schema", file=sys.stderr)
        return 1
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
