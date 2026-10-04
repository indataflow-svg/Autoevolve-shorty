#!/usr/bin/env python3
"""AutoEvolve video pipeline CLI.

Conceptually ``autoevolve video plan`` / ``autoevolve video queue``:

    .venv/bin/python scripts/video.py plan --script scripts/indataflow/corridor.md
    .venv/bin/python scripts/video.py queue <shot-plan-id>

``plan`` parses a prepared script into a VideoSpec and a ShotPlan, persists
both, and prints the RenderJob manifest (JSON). ``queue`` enqueues one
RenderJob per render-required shot and prints the queue summary. Planning is
deterministic; the AI layer only refines prompts when OMNIROUTE_API_KEY is set.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv

load_dotenv(REPO / ".env")


def _slug_for_script(path: Path) -> str:
    return "".join(char if char.isalnum() else "-" for char in path.stem.lower()).strip("-") or "video"


def command_plan(args: argparse.Namespace) -> int:
    from services import video_pipeline

    script = Path(args.script)
    if not script.is_file():
        print(f"error: script not found: {script}", file=sys.stderr)
        return 2
    project_id = args.project_id or _slug_for_script(script)
    try:
        result = video_pipeline.plan_video(
            script,
            project_id=project_id,
            campaign_id=args.campaign_id,
            aspect_ratio=args.format,
            fps=args.fps,
            use_ai=not args.no_ai,
            render_mode=args.mode,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    spec, plan, jobs = result["spec"], result["plan"], result["jobs"]
    print(f"VideoSpec  {spec['id']}  {spec['title']!r}  {spec['format']['durationSeconds']}s")
    print(f"ShotPlan   {plan['id']}  {len(plan['shots'])} shots  status={plan['status']}")
    print(f"AI layer   {result['ai']['source']}")
    manifest = {
        "spec_id": spec["id"],
        "shot_plan_id": plan["id"],
        "jobs": jobs,
    }
    if args.manifest_out:
        Path(args.manifest_out).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"manifest written: {args.manifest_out}")
    else:
        print(json.dumps(manifest, indent=2))
    return 0


def command_queue(args: argparse.Namespace) -> int:
    from services import video_pipeline

    try:
        result = video_pipeline.queue_shot_plan(
            args.shot_plan_id, priority=args.priority, render_mode=args.mode
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    counts = result["counts"]
    by_renderer = counts["by_renderer"]
    if result["already_queued"]:
        print(f"shot plan {args.shot_plan_id} is already queued")

    def jobs(noun: str, count: int) -> None:
        if count:
            print(f"{count} {noun} job{'s' if count != 1 else ''}")

    total = counts["total"]
    print(f"{total} job{'s' if total != 1 else ''} queued")
    jobs("Hunyuan", by_renderer.get("hunyuan", 0))
    jobs("asset/motion", by_renderer.get("asset", 0) + by_renderer.get("motion_graphics", 0))
    jobs("brand-end-frame", counts.get("brand_end_frames", 0))
    other_ffmpeg = by_renderer.get("ffmpeg", 0) - min(
        by_renderer.get("ffmpeg", 0), counts.get("brand_end_frames", 0)
    )
    jobs("ffmpeg", other_ffmpeg)
    return 0


def command_profile(_args: argparse.Namespace) -> int:
    from services import video_pipeline

    print(json.dumps(video_pipeline.hunyuan_profile(), indent=2))
    return 0


def command_submit(args: argparse.Namespace) -> int:
    from core import video_store
    from services import renderers

    try:
        job = renderers.submit_hunyuan_job(args.job_id, timeout_seconds=args.timeout)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except renderers.RenderWorkerError as exc:
        print(f"render failed ({exc.kind}): {exc}", file=sys.stderr)
        stored = video_store.get_job(args.job_id)
        if stored is not None:
            print(
                f"job {args.job_id} is now {stored['status']} "
                f"(attempts {stored['attempts']}/{stored['max_attempts']})",
                file=sys.stderr,
            )
        return 1
    result = job.get("result") or {}
    print(f"job {job['id']} completed: {result.get('outputPath')}")
    return 0


def command_worker_status(_args: argparse.Namespace) -> int:
    from services import renderers

    print(json.dumps(renderers.worker_status(), indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="parse a script into a VideoSpec, ShotPlan and job manifest")
    plan.add_argument("--script", required=True, help="path to the prepared script markdown")
    plan.add_argument("--project-id", default=None)
    plan.add_argument("--campaign-id", default=None)
    plan.add_argument("--format", default="9:16", choices=["4:5", "9:16", "16:9", "1:1"])
    plan.add_argument("--fps", type=int, default=24)
    plan.add_argument("--no-ai", action="store_true", help="skip AI prompt refinement even if configured")
    plan.add_argument("--mode", default="shots", choices=["shots", "full"],
                      help="shots: manifest per clip; full: single whole-video job")
    plan.add_argument("--manifest-out", default=None, help="write the job manifest JSON here instead of stdout")
    plan.set_defaults(func=command_plan)

    queue = sub.add_parser("queue", help="enqueue RenderJobs (per-shot clips or one full video)")
    queue.add_argument("shot_plan_id")
    queue.add_argument("--priority", type=int, default=100)
    queue.add_argument("--mode", default="shots", choices=["shots", "full"],
                       help="shots: one job per clip; full: single whole-video job, no clip division")
    queue.set_defaults(func=command_queue)

    profile = sub.add_parser("profile", help="print the default Hunyuan render profile")
    profile.set_defaults(func=command_profile)

    submit = sub.add_parser("submit", help="submit one queued hunyuan job to the MI300X worker")
    submit.add_argument("job_id")
    submit.add_argument("--timeout", type=int, default=None,
                        help="sync render budget in seconds (default RENDER_WORKER_TIMEOUT_SECONDS)")
    submit.set_defaults(func=command_submit)

    worker_status = sub.add_parser("worker-status", help="check MI300X worker health/capacity")
    worker_status.set_defaults(func=command_worker_status)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
