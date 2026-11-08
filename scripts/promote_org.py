#!/usr/bin/env python3
"""Promote the first real signup org to the paid/operator plan.

There is deliberately no seeded operator org. The operator signs up normally,
then this one-time command changes only that organization's plan.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--org", type=int, required=True)
    parser.add_argument("--plan", choices=("free", "paid"), default="paid")
    args = parser.parse_args()
    from core.state import connect, get_org

    org = get_org(args.org)
    if not org:
        print(f"org {args.org} not found", file=sys.stderr)
        return 1
    with connect() as db:
        db.execute(
            "UPDATE buffer_orgs SET plan = ?, updated_at = datetime('now') WHERE id = ?",
            (args.plan, args.org),
        )
    print(f"org {args.org} ({org['slug']}) -> {args.plan}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
