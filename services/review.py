"""Independent review stage (template-4 phases 14 and 15).

The creator never approves its own work here: technical review is fully
deterministic (ffprobe + job expectations), and the AI visual/continuity
reviewers run through the model-agnostic director interface, returning
SKIPPED — never a PASS — when no vision-capable model is configured.

Verdicts: PASS | REVISE | REGENERATE (deterministic finishing problems
yield REVISE, generation problems yield REGENERATE).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from services.renderers import RenderQAError, qa_render_output


def technical_review(path: str | Path, job: dict[str, Any]) -> dict[str, Any]:
    """Deterministic technical review of one rendered artifact."""
    critical: list[str] = []
    major: list[str] = []
    minor: list[str] = []
    details: dict[str, Any] = {}
    try:
        details = qa_render_output(
            path, expected_frames=job.get("frames"), expected_fps=job.get("fps")
        )
    except RenderQAError as exc:
        critical.append(str(exc))
    if not critical:
        width, height = details.get("width"), details.get("height")
        if job.get("width") and width != job["width"]:
            major.append(f"width {width} != expected {job['width']}")
        if job.get("height") and height != job["height"]:
            major.append(f"height {height} != expected {job['height']}")
        codec = str(details.get("codec") or "")
        if codec and codec not in ("h264", "avc", "hevc", "vp9"):
            minor.append(f"unusual codec for delivery: {codec}")
    if critical:
        status, score, recommendation = "REGENERATE", 0, "generation failed technical checks; regenerate the shot"
    elif major:
        status, score, recommendation = "REVISE", 70, "fix the flagged mismatch; regenerate only if it is baked into the render"
    else:
        status, score, recommendation = "PASS", 100 - 3 * len(minor), "technically sound"
    regeneration_changes: dict[str, Any] = {}
    if status == "REGENERATE" and job.get("seed") is not None:
        regeneration_changes = {"seed": job["seed"] + 1, "keep_prompt": True}
    return {
        "status": status,
        "score": max(0, score),
        "issues": {"critical": critical, "major": major, "minor": minor},
        "recommendation": recommendation,
        "regeneration_changes": regeneration_changes,
        "details": details,
    }


def ai_visual_review(artifact_path: str | Path, shot: dict[str, Any]) -> dict[str, Any]:
    """Vision-model review of one render. SKIPPED without a configured model."""
    from services.creative_director import CreativeDirector, DirectorUnavailable

    try:
        director = CreativeDirector(
            "visual_review",
            instructions=(
                "You are an independent video QC reviewer. Judge the described render "
                "against its shot specification for artifacts, subject integrity, motion, "
                "composition, lighting, brand consistency and text correctness. The same "
                "model that created the shot must not approve it: be adversarial. "
                "Return PASS only when nothing material is wrong."
            ),
        )
    except ValueError as exc:
        return _skipped(str(exc))
    try:
        from pydantic import BaseModel, Field

        class VisualVerdict(BaseModel):
            status: str = Field(pattern="^(PASS|REVISE|REGENERATE)$")
            score: int = Field(ge=0, le=100)
            issues: list[str] = Field(default_factory=list)
            recommendation: str = Field(default="", max_length=500)

        verdict = director.run(
            f"Shot spec: {shot.get('id')} {shot.get('purpose')}. "
            f"Prompt used: {(shot.get('visualPrompt') or '')[:600]}. "
            f"Artifact: {artifact_path} (local file, described, not attached). "
            "Review strictly from the spec; flag anything you cannot verify as an issue.",
            VisualVerdict,
        )
        return {
            "status": verdict.status,
            "score": verdict.score,
            "issues": {"critical": [], "major": verdict.issues, "minor": []},
            "recommendation": verdict.recommendation,
            "regeneration_changes": {},
        }
    except DirectorUnavailable as exc:
        return _skipped(str(exc))
    except Exception as exc:  # noqa: BLE001 - a failed reviewer abstains, never passes
        return _skipped(f"visual reviewer failed: {exc}")


def continuity_review(
    shots: list[dict[str, Any]], artifacts: dict[str, dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Deterministic cross-shot continuity check (codecs, fps, style chain).

    Detects the classic failure: shots that work individually but do not
    belong to the same film. Returns PASS/REVISE with concrete mismatches.
    """
    artifacts = artifacts or {}
    issues: list[str] = []
    codecs = {info.get("codec") for info in artifacts.values() if info.get("codec")}
    fps_values = {info.get("fps") for info in artifacts.values() if info.get("fps")}
    if len(codecs) > 1:
        issues.append(f"mixed codecs across shots: {sorted(codecs)}")
    if len(fps_values) > 1:
        issues.append(f"mixed frame rates across shots: {sorted(fps_values)}")
    chain = [shot.get("id") for shot in shots]
    for first, second in zip(chain, chain[1:]):
        first_next = next(
            (shot.get("continuity", {}).get("nextShot") for shot in shots if shot.get("id") == first),
            None,
        )
        if first_next != second:
            issues.append(f"continuity chain broken: {first} -> {first_next}, expected {second}")
    styles = {
        str((shot.get("continuity") or {}).get("style") or "") for shot in shots
    }
    if len(styles) > 1:
        issues.append("shots declare different continuity styles")
    if issues:
        return {"status": "REVISE", "issues": issues,
                "recommendation": "reconcile the mismatched shots before assembly"}
    return {"status": "PASS", "issues": [],
            "recommendation": "shots belong to the same film"}


def _skipped(reason: str) -> dict[str, Any]:
    return {
        "status": "SKIPPED",
        "score": 0,
        "issues": {"critical": [], "major": [], "minor": [reason]},
        "recommendation": "no vision-capable model configured; deterministic gates decide",
        "regeneration_changes": {},
    }
