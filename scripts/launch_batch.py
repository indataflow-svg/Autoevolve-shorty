#!/usr/bin/env python3
"""Plan a batch of product-launch videos from the researched brief set.

Each brief becomes its own VideoSpec, ShotPlan and single full-video RenderJob.
Plans only by default: --submit is opt-in so GPU is never spent without a
deliberate flag, and each job is submitted in sequence because the render worker
serves one synchronous render at a time.

Usage:
    .venv/bin/python scripts/launch_batch.py --dry-run          # plan, print, submit nothing
    .venv/bin/python scripts/launch_batch.py --only teaser      # plan one type
    .venv/bin/python scripts/launch_batch.py --submit --timeout 3600
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from launch_briefs import BRIEFS, RENDER_MODE  # noqa: E402

from services.video import pipeline as vp  # noqa: E402


def plan_one(key: str, project_id: str, submit: bool, timeout: int | None) -> dict:
    spec_meta = BRIEFS[key]
    brief = str(spec_meta["brief"])
    runtime = int(spec_meta["runtime"])
    result = vp.launch(
        brief=brief,
        project_id=project_id,
        submit=submit,
        timeout_seconds=timeout,
        render_mode=RENDER_MODE,
        runtime_seconds=runtime,
    )
    return {
        "key": key,
        "type": spec_meta["type"],
        "runtime": runtime,
        "spec_id": result.get("spec_id"),
        "shot_plan_id": result.get("shot_plan_id"),
        "title": result.get("title"),
        "counts": result.get("counts"),
        "jobs": [
            {
                "id": job.get("id"),
                "frames": job.get("frames"),
                "width": job.get("width"),
                "height": job.get("height"),
                "resolution": job.get("resolution"),
                "seed": job.get("seed"),
                "status": job.get("status"),
                "output_path": job.get("outputPath") or job.get("output_path"),
                "error": job.get("error"),
            }
            for job in result.get("jobs") or []
        ],
        "shots": result.get("shots") or [],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=sorted(BRIEFS), action="append")
    parser.add_argument("--batch-id", default="launch-batch-01")
    parser.add_argument("--submit", action="store_true")
    parser.add_argument("--timeout", type=int, default=3600)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    keys = args.only or list(BRIEFS)
    rows = []
    for key in keys:
        project_id = f"{args.batch_id}-{key}"
        print(f"\n=== {key} ({BRIEFS[key]['type']}, {BRIEFS[key]['runtime']}s)")
        try:
            row = plan_one(
                key, project_id, args.submit and not args.dry_run, args.timeout
            )
        except Exception as exc:  # keep planning the rest of the batch
            print(f"  FAILED: {exc}")
            rows.append({"key": key, "error": str(exc)})
            continue
        print(f"  title:  {row['title']}")
        print(f"  spec:   {row['spec_id']}  plan: {row['shot_plan_id']}")
        print(f"  counts: {row['counts']}")
        for job in row["jobs"]:
            print(
                f"  job:    {job['id']} {job['frames']}f "
                f"{job['width']}x{job['height']} res={job['resolution']} "
                f"seed={job['seed']} {job['status']} -> {job['output_path']}"
            )
            if job.get("error"):
                print(f"  error:  {job['error']}")
        rows.append(row)

    ok = [row for row in rows if not row.get("error")]
    print(f"\nplanned {len(ok)}/{len(rows)} videos")
    for row in ok:
        for job in row["jobs"]:
            print(f"  {job['status']:9} {job['id']}  {row['key']}")
    if args.dry_run and not args.submit:
        print("\ndry run: nothing submitted. Re-run with --submit to spend GPU.")
    return 0 if len(ok) == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
