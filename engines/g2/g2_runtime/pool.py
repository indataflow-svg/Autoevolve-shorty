from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import urllib.request
from pathlib import Path
from typing import Literal

from .fingerprint import file_sha256
from .models import AssetCandidate, StrictModel


PoolKind = Literal["product_demo", "face", "testimonial", "broll"]

VIDEO_SUFFIXES = {".mp4", ".mov", ".webm", ".m4v"}

# Which owned footage kinds fit each storyboard purpose. Ordered by preference:
# product_demo proves the claim, face/testimonial carries trust, broll fills.
KIND_BY_PURPOSE: dict[str, list[PoolKind]] = {
    "cover": ["face", "testimonial", "product_demo", "broll"],
    "evidence": ["product_demo", "face", "testimonial", "broll"],
    "operational_complexity": ["product_demo", "broll", "face", "testimonial"],
    "failure_point": ["face", "testimonial", "broll", "product_demo"],
    "control_system": ["product_demo", "broll", "face", "testimonial"],
    "outcome_cta": ["testimonial", "face", "product_demo", "broll"],
}


class PoolClip(StrictModel):
    clip_id: str
    file: str
    kind: PoolKind = "broll"
    description: str = ""
    transcript: str = ""
    topics: list[str] = []
    claims: list[str] = []
    goals: list[str] = []
    speaker: str | None = None
    consent: bool = False
    sha256: str | None = None
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None


def _terms(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{3,}", value.lower()))


def _pool_root(pool_path: str | Path) -> Path:
    return Path(pool_path).resolve().parent


def load_pool(pool_path: str | Path) -> dict:
    destination = Path(pool_path)
    if not destination.is_file():
        return {"clips": []}
    value = json.loads(destination.read_text(encoding="utf-8"))
    clips = value.get("clips", value) if isinstance(value, dict) else value
    return {"clips": [PoolClip.model_validate(item).model_dump(mode="json") for item in clips]}


def write_pool(clips: list[dict], pool_path: str | Path) -> Path:
    destination = Path(pool_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps({"clips": clips}, indent=2) + "\n", encoding="utf-8")
    return destination


def probe_video(path: Path) -> tuple[int | None, int | None, float | None]:
    """Width, height, duration via ffprobe. Returns Nones when ffprobe is missing."""
    if not shutil.which("ffprobe"):
        return None, None, None
    result = subprocess.run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height:format=duration", "-of", "json", str(path),
    ], check=True, capture_output=True, text=True)
    value = json.loads(result.stdout)
    stream = (value.get("streams") or [{}])[0]
    try:
        duration = float(value.get("format", {}).get("duration") or 0) or None
    except (TypeError, ValueError):
        duration = None
    return stream.get("width"), stream.get("height"), duration


def ingest_pool(pool_root: str | Path, pool_path: str | Path) -> dict:
    """Scan a drop-in directory for footage and register new files.

    New files get skeleton entries (kind=broll, consent=False) for the
    founder or `pool-tag` to enrich. Entries whose files vanished are
    reported and pruned. Never touches clip metadata the founder edited.
    """
    root = Path(pool_root).resolve()
    if not root.is_dir():
        raise ValueError(f"owned pool root is not a directory: {root}")
    existing = {item["clip_id"]: item for item in load_pool(pool_path)["clips"]}
    seen: set[str] = set()
    added, kept, missing = [], [], []
    for path in sorted(root.iterdir()):
        if not path.is_file() or path.suffix.lower() not in VIDEO_SUFFIXES or path.name.startswith("."):
            continue
        resolved = path.resolve()
        if resolved.parent != root:
            continue
        digest = file_sha256(path)
        clip_id = f"owned:{digest[:16]}"
        seen.add(clip_id)
        if clip_id in existing:
            kept.append(clip_id)
            continue
        try:
            width, height, duration = probe_video(path)
        except Exception:
            width, height, duration = None, None, None
        existing[clip_id] = PoolClip(
            clip_id=clip_id,
            file=path.name,
            description=path.stem.replace("_", " ").replace("-", " "),
            sha256=digest,
            duration_seconds=duration,
            width=width,
            height=height,
        ).model_dump(mode="json")
        added.append(clip_id)
    for clip_id in [key for key in existing if key not in seen]:
        missing.append(clip_id)
        del existing[clip_id]
    clips = [existing[key] for key in sorted(existing)]
    write_pool(clips, pool_path)
    return {"ok": True, "pool": str(pool_path), "added": added, "kept": kept,
            "missing_pruned": missing, "total": len(clips)}


def _clip_text(clip: PoolClip) -> str:
    return " ".join([clip.description, clip.transcript, *clip.topics, *clip.claims, *clip.goals,
                     clip.kind, clip.speaker or ""])


def clip_to_candidate(clip: PoolClip, pool_root: str | Path, query: str = "") -> AssetCandidate:
    root = Path(pool_root).resolve()
    local_path = (root / clip.file).resolve()
    width = clip.width or 1
    height = clip.height or 1
    return AssetCandidate(
        candidate_id=clip.clip_id, provider="owned", source_type="owned",
        media_type="video", query=query,
        description=(clip.description + (" | " + clip.transcript[:280] if clip.transcript else "")).strip(" |"),
        tags=[clip.kind, *clip.topics, *clip.claims, *clip.goals],
        local_path=str(local_path), license="owned footage (consent on file)" if clip.consent else "owned footage (consent PENDING)",
        width=width, height=height, duration_seconds=clip.duration_seconds,
    )


class OwnedPoolProvider:
    """Federated-search-compatible provider over the owned footage pool.

    Same `.search(query, limit, media_type)` interface as the stock
    providers, so it slots into FederatedMediaSearch. Only consent-cleared
    clips are returned; ranking bonuses come from match_for_scene.
    """

    def __init__(self, pool_path: str | Path):
        self.pool_path = Path(pool_path)
        self.pool_root = _pool_root(pool_path)

    def clips(self) -> list[PoolClip]:
        return [PoolClip.model_validate(item) for item in load_pool(self.pool_path)["clips"]]

    def search(self, query: str, limit: int = 5, media_type: str = "video") -> list[AssetCandidate]:
        if media_type != "video":
            return []
        query_terms = _terms(query)
        scored: list[tuple[int, AssetCandidate]] = []
        for clip in self.clips():
            if not clip.consent:
                continue
            local_path = (self.pool_root / clip.file).resolve()
            if not local_path.is_file():
                continue
            metadata = _terms(_clip_text(clip))
            overlap = len(query_terms & metadata)
            if query_terms and not overlap:
                continue
            scored.append((overlap, clip_to_candidate(clip, self.pool_root, query)))
        scored.sort(key=lambda pair: (-pair[0], pair[1].candidate_id))
        return [candidate for _, candidate in scored[:limit]]


def match_for_scene(
    clips: list[PoolClip],
    *,
    purpose: str,
    queries: list[str],
    narration: str = "",
    goal: str = "",
    claim_ids: list[str] | None = None,
    duration_seconds: float = 6.0,
    orientation: str = "portrait",
    minimum_width: int = 1080,
    minimum_height: int = 1920,
    limit: int = 3,
) -> list[dict]:
    """Context-aware owned-footage ranking for one storyboard scene.

    Connects the scene's purpose + claim IDs + narration + campaign goal
    to clip topics/claims/goals. Returns [{clip, candidate, score, reasons}].
    Clips without consent are excluded with an explicit reason.
    """
    claim_ids = claim_ids or []
    query_terms = set().union(*(_terms(value) for value in [*queries, narration])) if [*queries, narration] else set()
    goal_terms = _terms(goal)
    ranked = []
    for clip in clips:
        clip_terms = _terms(_clip_text(clip))
        reasons: list[str] = []
        if not clip.consent:
            ranked.append({"clip_id": clip.clip_id, "score": 0.0,
                           "reasons": ["consent pending — excluded from selection"], "candidate": None})
            continue
        score = 0.0
        clip_claims = {item.lower() for item in clip.claims}
        matched_claims = sorted({item for item in claim_ids if item.lower() in clip_claims})
        if claim_ids and matched_claims:
            score += 0.35
            reasons.append("claim grounded on camera: " + ", ".join(matched_claims))
        overlap = len(query_terms & clip_terms) / max(1, len(query_terms)) if query_terms else 0.0
        score += min(overlap * 0.45, 0.30)
        if overlap:
            reasons.append(f"topic/context overlap {overlap:.2f}")
        preferred = KIND_BY_PURPOSE.get(purpose, [])
        if clip.kind in preferred:
            bonus = 0.15 * (1 - preferred.index(clip.kind) / max(1, len(preferred)))
            score += bonus
            reasons.append(f"kind {clip.kind} fits {purpose} (+{bonus:.2f})")
        if goal_terms and (goal_terms & clip_terms):
            score += 0.10
            reasons.append("campaign goal match")
        width, height = clip.width or 0, clip.height or 0
        if width and height:
            portrait = height >= width
            if (orientation == "portrait") == portrait:
                score += 0.08
                reasons.append("native orientation")
            scale = min(width / max(1, minimum_width), height / max(1, minimum_height))
            if scale >= 1.0:
                score += 0.07
                reasons.append("delivery resolution")
            elif scale < 0.67:
                score -= 0.10
                reasons.append("below delivery resolution")
        if clip.duration_seconds:
            if clip.duration_seconds >= duration_seconds:
                score += 0.10
                reasons.append("covers timed unit")
            elif clip.duration_seconds >= max(2.0, duration_seconds * 0.5):
                score += 0.03
                reasons.append("short but usable")
            else:
                score -= 0.10
                reasons.append("too short for timed unit")
        ranked.append({"clip_id": clip.clip_id, "score": round(max(0.0, min(score, 1.0)), 4),
                       "reasons": reasons, "candidate": None})
    ranked.sort(key=lambda item: (-item["score"], item["clip_id"]))
    return ranked[:limit]


class OmniRouteChat:
    """Minimal OpenAI-compatible chat client for pool tagging (no G1 store)."""

    def __init__(self, base_url: str | None = None, api_key: str | None = None,
                 model: str | None = None, timeout: int = 90):
        self.base_url = (base_url or os.getenv("OMNIROUTE_BASE_URL", "http://127.0.0.1:20128/v1")).rstrip("/")
        self.api_key = api_key if api_key is not None else os.getenv("CODING_API_KEY", "")
        self.model = model or os.getenv("G2_TAG_MODEL", "auto/best-fast")
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def complete_json(self, system: str, user: str) -> dict:
        if not self.api_key:
            raise RuntimeError("CODING_API_KEY is not configured")
        payload = {"model": self.model,
                   "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                   "response_format": {"type": "json_object"}, "temperature": 0.2, "stream": False}
        request = urllib.request.Request(
            self.base_url + "/chat/completions", data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json",
                     "Accept": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            body = json.loads(response.read().decode("utf-8", errors="replace"))
        choices = body.get("choices") or []
        if not choices:
            raise ValueError("tagging model returned no choices")
        content = (choices[0].get("message") or {}).get("content") or ""
        text = content.strip()
        if text.startswith("```"):
            lines = text.splitlines()[1:]
            if lines and lines[-1].strip() == "```":
                lines.pop()
            text = "\n".join(lines).strip()
        return json.loads(text)


TAG_SYSTEM = (
    "You tag owned marketing footage for a video engine. Given a clip's filename, "
    "founder description, and transcript, return exactly one JSON object with keys: "
    "kind (product_demo|face|testimonial|broll), topics (2-6 short lowercase tags of what is "
    "visibly shown or discussed), claims (IDs from the provided claim list that are literally "
    "demonstrated on camera, never inferred), goals (subset of awareness|education|walkthrough|trial "
    "this clip could serve), speaker (name if stated, else null), description (one sentence). "
    "When unsure, prefer kind=broll and empty claims. Never invent claims."
)


def tag_clips(pool_path: str | Path, model=None, claim_ids: list[str] | None = None,
              force: bool = False, limit: int = 25) -> dict:
    """AI-tag untagged pool clips: topics, claims, kind, goal fit.

    Skips clips that already have topics unless force=True. Model must
    expose complete_json(system, user); defaults to OmniRouteChat.
    """
    model = model or OmniRouteChat()
    if not model.configured:
        raise RuntimeError("tagging model is not configured (CODING_API_KEY)")
    pool = load_pool(pool_path)
    tagged, skipped, failed = [], [], []
    for item in pool["clips"]:
        if len(tagged) >= limit:
            break
        clip = PoolClip.model_validate(item)
        if clip.topics and not force:
            skipped.append(clip.clip_id)
            continue
        user = json.dumps({
            "file": clip.file,
            "description": clip.description,
            "transcript": clip.transcript[:2000],
            "claim_ids": claim_ids or [],
        }, ensure_ascii=False)
        try:
            data = model.complete_json(TAG_SYSTEM, user)
        except Exception as exc:
            failed.append({"clip_id": clip.clip_id, "error": f"{type(exc).__name__}: {exc}"})
            continue
        kind = str(data.get("kind") or "broll")
        updates = {
            "kind": kind if kind in ("product_demo", "face", "testimonial", "broll") else "broll",
            "topics": [str(item) for item in (data.get("topics") or [])][:8],
            "claims": [str(item) for item in (data.get("claims") or []) if not claim_ids or str(item) in claim_ids][:8],
            "goals": [str(item) for item in (data.get("goals") or [])
                       if str(item) in ("awareness", "education", "walkthrough", "trial")][:4],
            "speaker": data.get("speaker"),
            "description": str(data.get("description") or clip.description)[:280],
        }
        item.update(updates)
        tagged.append(clip.clip_id)
    write_pool(pool["clips"], pool_path)
    return {"ok": True, "pool": str(pool_path), "tagged": tagged, "skipped": skipped,
            "failed": failed, "total": len(pool["clips"])}


def pool_fingerprint(pool_path: str | Path) -> str:
    return hashlib.sha256(
        json.dumps(load_pool(pool_path), ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
