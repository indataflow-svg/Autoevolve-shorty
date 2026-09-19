from __future__ import annotations

import hashlib
import json
import mimetypes
import os
from datetime import datetime, timezone
from typing import Any, Protocol

from .accounts import BufferAccount
from .buffer import BufferClient
from .errors import G3Error
from .handoff import Entry, Handoff, Media
from .ledger import Ledger


SCHEDULE_MODES = {
    "queue": ("automatic", "addToQueue"),
    "next": ("automatic", "shareNext"),
    "timed": ("custom", "customScheduled"),
}


class Uploader(Protocol):
    def upload(self, campaign_id: str, media: Media) -> str: ...


def channel_id(entry: Entry, account: BufferAccount | None = None) -> str:
    if entry.channel_id:
        return entry.channel_id
    if account is not None:
        return account.channel_for(entry.platform)
    key = "BUFFER_X_CHANNEL_ID" if entry.platform == "x" else "BUFFER_INSTAGRAM_CHANNEL_ID"
    value = os.environ.get(key, "").strip()
    if not value:
        raise G3Error(f"missing {key} and no integration_id in handoff")
    return value


def parse_due_at(value: str | None) -> str | None:
    """Normalize a scheduling timestamp to UTC ISO-8601. Must be in the future."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00") if text.endswith(("Z", "z")) else text
    try:
        moment = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise G3Error(f"dueAt is not a valid ISO-8601 timestamp: {text!r}") from exc
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    moment = moment.astimezone(timezone.utc)
    if moment <= datetime.now(timezone.utc):
        raise G3Error("dueAt must be in the future")
    return moment.isoformat(timespec="seconds").replace("+00:00", "Z")


def idempotency_key(handoff: Handoff, entry: Entry, resolved_id: str) -> str:
    stable = {
        "source": handoff.source_package_sha256,
        "campaign": handoff.campaign_id,
        "platform": entry.platform,
        "channel": resolved_id,
        "content": [
            {"content": part["content"], "media": [media.sha256 for media in part["media"]]}
            for part in entry.values
        ],
    }
    return hashlib.sha256(json.dumps(stable, sort_keys=True).encode()).hexdigest()


def schedule_key(handoff: Handoff, entry: Entry, resolved_id: str, mode: str,
                 due_at: str | None, account: str = "default") -> str:
    base = idempotency_key(handoff, entry, resolved_id)
    return hashlib.sha256(f"{base}|schedule|{account}|{mode}|{due_at or ''}".encode()).hexdigest()


def _asset(url: str, media: Media) -> dict[str, Any]:
    mime = mimetypes.guess_type(media.path.name)[0] or ""
    return {"video" if mime == "video/mp4" else "image": {"url": url}}


def build_input(entry: Entry, resolved_id: str, urls: list[list[str]]) -> dict[str, Any]:
    parts = []
    for part, part_urls in zip(entry.values, urls, strict=True):
        assets = [_asset(url, media) for url, media in zip(part_urls, part["media"], strict=True)]
        parts.append({"text": part["content"], "assets": assets})

    result: dict[str, Any] = {
        "channelId": resolved_id,
        "text": parts[0]["text"],
        "assets": parts[0]["assets"],
        "schedulingType": "automatic",
        "mode": "addToQueue",
        "saveToDraft": True,
        "needsApproval": False,
        "source": "company-core-g3",
    }
    if entry.platform.startswith("instagram"):
        result["metadata"] = {"instagram": {"type": "post", "shouldShareToFeed": True}}
    elif entry.platform == "x" and len(parts) > 1:
        result["metadata"] = {"twitter": {"thread": parts}}
    return result


def build_schedule_input(entry: Entry, resolved_id: str, urls: list[list[str]],
                         *, mode: str, due_at: str | None = None) -> dict[str, Any]:
    """Build a Buffer createPost input that schedules instead of drafting.

    Scheduling intent travels via explicit arguments (CLI/API), never via the
    handoff file — the handoff schema still rejects scheduling fields, so a
    draft can never silently become a scheduled post.
    """
    if mode not in SCHEDULE_MODES:
        raise G3Error(f"unknown scheduling mode {mode!r}: expected one of {sorted(SCHEDULE_MODES)}")
    normalized_due_at = parse_due_at(due_at)
    if mode == "timed" and not normalized_due_at:
        raise G3Error("timed scheduling requires a future dueAt timestamp")
    if mode != "timed" and normalized_due_at:
        raise G3Error(f"dueAt is only valid with timed scheduling, not {mode!r}")
    scheduling_type, buffer_mode = SCHEDULE_MODES[mode]
    result = build_input(entry, resolved_id, urls)
    result.update({
        "schedulingType": scheduling_type,
        "mode": buffer_mode,
        "saveToDraft": False,
    })
    if normalized_due_at:
        result["dueAt"] = normalized_due_at
    return result


def submit_schedule(client: BufferClient, uploader: Uploader | None, ledger: Ledger,
                    handoff: Handoff, mode: str, due_at: str | None,
                    dry_run: bool = False, account: BufferAccount | None = None) -> dict[str, Any]:
    normalized_due_at = parse_due_at(due_at) if mode == "timed" else None
    if mode == "timed" and not normalized_due_at:
        raise G3Error("timed scheduling requires a future dueAt timestamp")
    account_name = account.name if account else "default"
    report: dict[str, Any] = {
        "ok": True, "campaign_id": handoff.campaign_id, "provider": "buffer",
        "draft_only": False, "scheduled": True, "mode": mode, "due_at": normalized_due_at,
        "account": account_name,
        "publish_allowed": False, "results": [],
    }
    for entry in handoff.entries:
        resolved_id = channel_id(entry, account)
        key = schedule_key(handoff, entry, resolved_id, mode, normalized_due_at, account_name)
        old_post = ledger.existing(key)
        if old_post:
            report["results"].append(
                {"platform": entry.platform, "status": "duplicate_skipped", "post_id": old_post}
            )
            continue
        urls: list[list[str]] = []
        for part in entry.values:
            if dry_run:
                urls.append([f"https://dry.invalid/{media.sha256}/{media.path.name}" for media in part["media"]])
            else:
                if uploader is None:
                    raise G3Error("media uploader is required")
                urls.append([uploader.upload(handoff.campaign_id, media) for media in part["media"]])
        post_input = build_schedule_input(entry, resolved_id, urls, mode=mode, due_at=normalized_due_at)
        if dry_run:
            report["results"].append(
                {"platform": entry.platform, "status": "dry_run", "buffer_input": post_input}
            )
            continue
        post = client.create_scheduled(post_input)
        post_id = str(post["id"])
        ledger.record(key, handoff.campaign_id, entry.platform, post_id)
        report["results"].append(
            {"platform": entry.platform, "status": "scheduled",
             "post_id": post_id, "buffer_status": post.get("status"),
             "due_at": post.get("dueAt") or normalized_due_at}
        )
    return report


def submit_handoff(client: BufferClient, uploader: Uploader | None, ledger: Ledger,
                   handoff: Handoff, dry_run: bool = False,
                   account: BufferAccount | None = None) -> dict[str, Any]:
    report: dict[str, Any] = {
        "ok": True, "campaign_id": handoff.campaign_id, "provider": "buffer",
        "draft_only": True, "publish_allowed": False,
        "account": account.name if account else "default",
        "results": [],
    }
    for entry in handoff.entries:
        resolved_id = channel_id(entry, account)
        key = idempotency_key(handoff, entry, resolved_id)
        old_post = ledger.existing(key)
        if old_post:
            report["results"].append(
                {"platform": entry.platform, "status": "duplicate_skipped", "post_id": old_post}
            )
            continue
        urls: list[list[str]] = []
        for part in entry.values:
            if dry_run:
                urls.append([f"https://dry.invalid/{media.sha256}/{media.path.name}" for media in part["media"]])
            else:
                if uploader is None:
                    raise G3Error("media uploader is required")
                urls.append([uploader.upload(handoff.campaign_id, media) for media in part["media"]])
        post_input = build_input(entry, resolved_id, urls)
        if post_input.get("saveToDraft") is not True or "dueAt" in post_input:
            raise G3Error("internal draft-only invariant failed")
        if dry_run:
            report["results"].append(
                {"platform": entry.platform, "status": "dry_run", "buffer_input": post_input}
            )
            continue
        post = client.create_draft(post_input)
        post_id = str(post["id"])
        ledger.record(key, handoff.campaign_id, entry.platform, post_id)
        report["results"].append(
            {"platform": entry.platform, "status": "draft_confirmed", "post_id": post_id}
        )
    return report
