"""Signed webhook publisher.

Contract (all requests are JSON, HMAC-SHA256 signed):

    POST <PUBLISHER_WEBHOOK_URL>
    X-Publisher-Signature: sha256=<hex digest of the raw body>
    X-Idempotency-Key: manual-post:<post id>:<action>:<account>:<mode>:<due_at>

    {"schema":"company-core.publisher.webhook.v1",
     "action":"schedule"|"status"|"insights",
     "publisher":"webhook",
     "account":"...",
     "post": {...},
     "schedule": {"mode":"queue", "due_at": null}}

The receiver must answer with a JSON object:

    {"ok": true, "post_id": "external-id", "status": "scheduled",
     "external_url": "https://...", "due_at": "...", "metrics": [...]}

`post_id` is required for `schedule`. `status`/`insights` are best-effort
provider reads; the local record is only marked sent when the receiver
explicitly says `"status":"sent"`.

Media is exposed through short-lived signed URLs built from PUBLIC_BASE_URL;
the receiver does not need access to local files.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import mimetypes
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from .base import PublisherAccount, PublisherCapabilities, PublisherError


SCHEMA = "company-core.publisher.webhook.v1"
DEFAULT_PLATFORMS = ("instagram", "x", "linkedin")


@dataclass(frozen=True)
class WebhookConfig:
    url: str
    secret: str
    account: str
    label: str
    platforms: tuple[str, ...]
    base_url: str
    timeout: float
    asset_ttl: int

    @property
    def configured(self) -> bool:
        return bool(self.url and self.secret)


def load_config(org_id: int | None = None) -> WebhookConfig:
    from core.auth_context import current_org_id

    effective_org = org_id if org_id is not None else current_org_id.get()
    timeout = float(os.getenv("PUBLISHER_WEBHOOK_TIMEOUT_SECONDS", "30"))
    asset_ttl = int(os.getenv("PUBLISHER_WEBHOOK_ASSET_TTL_SECONDS", "3600"))
    base_url = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if effective_org:
        from core.publishers_store import webhook_for_org

        connection = webhook_for_org(int(effective_org))
        if connection:
            return WebhookConfig(
                url=connection["url"],
                secret=connection["secret"],
                account=connection["account"],
                label=connection["label"],
                platforms=tuple(connection["platforms"]) or DEFAULT_PLATFORMS,
                base_url=base_url,
                timeout=timeout,
                asset_ttl=asset_ttl,
            )
        # Paid/operator orgs may still use the deployment-level webhook. Free
        # orgs never inherit it: their publishing credential is their own.
        from core.state import get_org

        org = get_org(int(effective_org))
        if not org or (org.get("plan") or "paid") == "free":
            return WebhookConfig(
                url="", secret="", account="webhook", label="Webhook scheduler",
                platforms=DEFAULT_PLATFORMS, base_url=base_url, timeout=timeout, asset_ttl=asset_ttl,
            )
    platforms = tuple(
        part.strip().lower()
        for part in os.getenv("PUBLISHER_WEBHOOK_PLATFORMS", ",".join(DEFAULT_PLATFORMS)).split(",")
        if part.strip()
    )
    return WebhookConfig(
        url=os.getenv("PUBLISHER_WEBHOOK_URL", "").strip(),
        secret=os.getenv("PUBLISHER_WEBHOOK_SECRET", "").strip(),
        account=os.getenv("PUBLISHER_WEBHOOK_ACCOUNT", "webhook").strip() or "webhook",
        label=os.getenv("PUBLISHER_WEBHOOK_LABEL", "Webhook scheduler").strip() or "Webhook scheduler",
        platforms=platforms or DEFAULT_PLATFORMS,
        base_url=base_url,
        timeout=timeout,
        asset_ttl=asset_ttl,
    )


def _post(post_id: str) -> dict[str, Any]:
    from core.marketing_store import get_manual_post

    post = get_manual_post(post_id)
    if not post:
        raise PublisherError("manual post not found", 404)
    return post


def _status(post: dict[str, Any]) -> str:
    from app.marketing_api import _manual_post_status

    return _manual_post_status(post)


def _classify(raw: object) -> str:
    from app.marketing_api import _classify_provider_status

    return _classify_provider_status(raw)


def _update(post_id: str, metadata: dict[str, Any]) -> dict[str, Any]:
    from core.marketing_store import update_manual_post

    updated = update_manual_post(post_id, metadata_json=json.dumps(metadata, ensure_ascii=False))
    return updated


def _public(updated: dict[str, Any]) -> dict[str, Any]:
    from app.marketing_api import _public_manual_post

    return _public_manual_post(updated)


def _signature(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _send(action: str, payload: dict[str, Any], *, idempotency_key: str, org_id: int = 0) -> dict[str, Any]:
    config = load_config(org_id or None)
    if not config.configured:
        raise PublisherError("webhook publisher is not configured (set PUBLISHER_WEBHOOK_URL and PUBLISHER_WEBHOOK_SECRET)", 503)
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-Publisher-Signature": _signature(body, config.secret),
        "X-Idempotency-Key": idempotency_key,
    }
    try:
        response = httpx.post(config.url, content=body, headers=headers, timeout=config.timeout)
    except httpx.HTTPError as exc:
        raise PublisherError(f"webhook scheduler unreachable: {type(exc).__name__}: {exc}", 502) from exc
    if response.status_code >= 400:
        detail = (response.text or "no response body").strip()[:500]
        raise PublisherError(f"webhook scheduler returned HTTP {response.status_code}: {detail}", 502)
    try:
        data = response.json()
    except ValueError as exc:
        raise PublisherError("webhook scheduler returned non-JSON", 502) from exc
    if not isinstance(data, dict):
        raise PublisherError("webhook scheduler returned a non-object JSON body", 502)
    if data.get("ok") is False:
        raise PublisherError(str(data.get("error") or "webhook scheduler rejected the request"), 502)
    return data


def asset_token(post_id: str, index: int, expires_at: int, org_id: int | None = None) -> str:
    config = load_config(org_id)
    if not config.secret:
        raise PublisherError("webhook publisher is not configured", 503)
    message = f"{post_id}:{index}:{expires_at}".encode("utf-8")
    return hmac.new(config.secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def verify_asset_token(
    post_id: str, index: int, expires_at: int, token: str, org_id: int | None = None
) -> None:
    if expires_at < int(time.time()):
        raise PublisherError("asset link expired", 410)
    expected = asset_token(post_id, index, expires_at, org_id)
    if not secrets.compare_digest(expected, token or ""):
        raise PublisherError("invalid asset link", 403)


def _asset_path(post: dict[str, Any], index: int) -> tuple[Path, dict[str, Any]]:
    if index < 0:
        raise PublisherError("asset index out of range", 404)
    assets = post.get("assets") or []
    if index >= len(assets):
        raise PublisherError("asset index out of range", 404)
    asset = dict(assets[index])
    asset_dir = Path(str(post.get("asset_dir") or "")).resolve()
    try:
        from app.marketing_api import PROJECTS_ROOT

        asset_dir.relative_to(PROJECTS_ROOT)
    except ValueError as exc:
        raise PublisherError("asset path is outside the company workspace", 403) from exc
    filename = Path(str(asset.get("filename") or "")).name
    if not filename:
        raise PublisherError("asset has no filename", 404)
    path = (asset_dir / filename).resolve()
    try:
        path.relative_to(asset_dir)
    except ValueError as exc:
        raise PublisherError("asset path escapes the post directory", 403) from exc
    if not path.is_file():
        raise PublisherError("asset file is missing", 404)
    return path, asset


def public_asset(post_id: str, index: int, expires_at: int, token: str) -> tuple[Path, str, str]:
    """Resolve a signed public asset link. Used by the unauthenticated route."""
    post = _post(post_id)
    verify_asset_token(post_id, index, expires_at, token, int(post.get("org_id") or 0))
    path, asset = _asset_path(post, index)
    content_type = str(
        asset.get("content_type")
        or mimetypes.guess_type(path.name)[0]
        or "application/octet-stream"
    )
    return path, path.name, content_type


def _media(post: dict[str, Any], config: WebhookConfig) -> list[dict[str, Any]]:
    if not (post.get("assets") or []):
        return []
    if not config.base_url:
        raise PublisherError(
            "PUBLIC_BASE_URL is required so a webhook scheduler can fetch media", 409
        )
    expires_at = int(time.time()) + max(60, config.asset_ttl)
    media = []
    for index, asset in enumerate(post.get("assets") or []):
        token = asset_token(post["id"], index, expires_at)
        filename = str(asset.get("filename") or "")
        path, _ = _asset_path(post, index)
        media.append({
            "index": index,
            "filename": filename,
            "content_type": str(asset.get("content_type") or mimetypes.guess_type(path.name)[0] or "application/octet-stream"),
            "size_bytes": path.stat().st_size,
            "url": f"{config.base_url}/public/manual-posts/{quote(post['id'], safe='')}/assets/{index}"
                   f"?exp={expires_at}&token={token}",
            "expires_at": expires_at,
        })
    return media


def _post_payload(post: dict[str, Any]) -> dict[str, Any]:
    metadata = post.get("metadata") or {}
    return {
        "id": str(post.get("id")),
        "post_id": str(post.get("post_id") or post.get("id")),
        "platform": str(post.get("platform") or ""),
        "post_type": str(metadata.get("post_type") or "carousel"),
        "caption": str(metadata.get("generated_caption") or post.get("creative") or ""),
        "title": str(post.get("title") or metadata.get("generated_title") or ""),
        "tracked_url": str(post.get("tracked_url") or ""),
        "destination_url": str(post.get("destination_url") or metadata.get("destination_url") or ""),
        "campaign_id": post.get("campaign_id") or metadata.get("generated_campaign_id"),
        "source_detail": str(post.get("source_detail") or ""),
    }


class WebhookPublisher:
    name = "webhook"
    label = "Webhook scheduler"

    def capabilities(self) -> PublisherCapabilities:
        config = load_config()
        return PublisherCapabilities(
            draft=False,
            schedule=True,
            confirm=True,
            insights=True,
            platforms=config.platforms,
        )

    def accounts(self) -> list[PublisherAccount]:
        config = load_config()
        if not config.configured:
            return []
        return [
            PublisherAccount(
                name=config.account,
                label=config.label,
                platforms=config.platforms,
                details={"publisher": self.name, "configured": True},
            )
        ]

    def draft(self, post: dict[str, Any], account: str | None = None) -> dict[str, Any]:
        raise PublisherError("the webhook publisher supports scheduling, not drafts", 409)

    def schedule(
        self,
        post: dict[str, Any],
        *,
        account: str | None = None,
        mode: str = "queue",
        due_at: str | None = None,
    ) -> dict[str, Any]:
        org_id = int(post.get("org_id") or 0)
        config = load_config(org_id or None)
        if not config.configured:
            raise PublisherError("webhook publisher is not configured", 503)
        if mode not in {"queue", "next", "timed"}:
            raise PublisherError("mode must be queue, next, or timed", 422)
        if mode == "timed" and not due_at:
            raise PublisherError("timed scheduling requires due_at", 422)
        if _status(post) not in {"ready", "buffer_draft", "scheduled"}:
            raise PublisherError("finalize the manual post before scheduling it", 409)
        platform = str(post.get("platform") or "").lower()
        if platform not in config.platforms:
            raise PublisherError(f"webhook publisher does not support platform {platform!r}", 422)
        if not (post.get("assets") or []):
            raise PublisherError("upload and finalize at least one asset before scheduling", 422)
        from core.quotas import QuotaExceeded, enforce_quota, record_usage

        org_id = int(post.get("org_id") or 0)
        try:
            enforce_quota(org_id, "publishes")
        except QuotaExceeded as exc:
            raise PublisherError(str(exc), 429) from exc
        selected_account = account or config.account
        payload = {
            "schema": SCHEMA,
            "action": "schedule",
            "publisher": self.name,
            "account": selected_account,
            "post": _post_payload(post),
            "media": _media(post, config),
            "schedule": {"mode": mode, "due_at": due_at if mode == "timed" else None},
        }
        data = _send(
            "schedule",
            payload,
            idempotency_key=f"manual-post:{post['id']}:schedule:{selected_account}:{mode}:{due_at or ''}",
            org_id=org_id,
        )
        external_id = str(data.get("post_id") or "").strip()
        if not external_id:
            raise PublisherError("webhook scheduler did not return post_id", 502)
        metadata = dict(post.get("metadata") or {})
        metadata.update({
            "publisher": self.name,
            "publisher_status": "scheduled",
            "publisher_account": selected_account,
            "publisher_post_ids": [external_id],
            "publisher_result": data,
            "publisher_schedule_mode": mode,
            "publisher_scheduled_at": due_at if mode == "timed" else None,
            "workflow_status": "scheduled",
        })
        updated = _update(post["id"], metadata)
        record_usage(org_id, "publishes", f"{post['id']}:{external_id}")
        when = f" for {due_at}" if mode == "timed" else ""
        return {
            "ok": True,
            "post": _public(updated),
            "result": data,
            "message": f"{config.label} accepted the post{when} (post id {external_id}).",
        }

    def confirm(self, post: dict[str, Any]) -> dict[str, Any]:
        org_id = int(post.get("org_id") or 0)
        config = load_config(org_id or None)
        metadata = dict(post.get("metadata") or {})
        saved_ids = [str(value) for value in metadata.get("publisher_post_ids") or [] if value]
        if not saved_ids:
            raise PublisherError("this manual post has no scheduled webhook post to confirm", 409)
        entries: dict[str, dict[str, Any]] = {}
        for post_id in saved_ids:
            try:
                data = _send(
                    "status",
                    {
                        "schema": SCHEMA,
                        "action": "status",
                        "publisher": self.name,
                        "account": metadata.get("publisher_account") or config.account,
                        "post_id": post_id,
                    },
                    idempotency_key=f"manual-post:{post['id']}:status:{post_id}",
                    org_id=org_id,
                )
            except PublisherError as exc:
                entries[post_id] = {"status": "unknown", "verdict": "unknown", "error": str(exc)}
                continue
            raw_status = str(data.get("status") or "unknown")
            entries[post_id] = {
                "status": raw_status,
                "verdict": _classify(raw_status),
                "due_at": data.get("due_at"),
                "external_link": data.get("external_url"),
                "metrics": data.get("metrics"),
            }
        verdicts = {entry["verdict"] for entry in entries.values()}
        if verdicts == {"sent"}:
            overall = "sent"
        elif "failed" in verdicts:
            overall = "failed"
        elif "unknown" in verdicts:
            overall = "unknown"
        else:
            overall = "pending"
        confirmation = {
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
            "overall": overall,
            "posts": entries,
        }
        metadata["publisher_send_confirmation"] = confirmation
        updated = _update(post["id"], metadata)
        return {
            "ok": True,
            "post": _public(updated),
            "confirmation": confirmation,
            "message": f"{config.label} reports: {overall}.",
        }

    def insights(self, post: dict[str, Any], post_id: str) -> dict[str, Any]:
        org_id = int(post.get("org_id") or 0)
        config = load_config(org_id or None)
        metadata = dict(post.get("metadata") or {})
        saved_ids = [str(value) for value in metadata.get("publisher_post_ids") or [] if value]
        if post_id not in saved_ids:
            raise PublisherError("post ID is not saved for this manual post", 404)
        data = _send(
            "insights",
            {
                "schema": SCHEMA,
                "action": "insights",
                "publisher": self.name,
                "account": metadata.get("publisher_account") or config.account,
                "post_id": post_id,
            },
            idempotency_key=f"manual-post:{post['id']}:insights:{post_id}",
            org_id=org_id,
        )
        return {
            "post_id": post_id,
            "buffer_account": metadata.get("publisher_account") or config.account,
            "status": str(data.get("status") or "unknown"),
            "due_at": data.get("due_at"),
            "external_link": data.get("external_url"),
            "metrics": data.get("metrics"),
            "metrics_updated_at": data.get("metrics_updated_at"),
            "experimental": True,
            "publisher": self.name,
        }
