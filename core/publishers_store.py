"""Per-organization publisher connections.

The signed webhook is the first non-Buffer adapter and the free-plan publish
path. Secrets are encrypted at rest with a key derived from
``APP_ENCRYPTION_KEY``; rotating that key makes old secrets unreadable by
design, so keep it stable.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from typing import Any
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken

from core.state import connect, now_iso

DEFAULT_PLATFORMS = ("instagram", "x", "linkedin")


def _fernet() -> Fernet:
    material = (os.getenv("APP_ENCRYPTION_KEY") or "").strip()
    if not material:
        material = "|".join(
            [
                os.getenv("DASHBOARD_PASSWORD", ""),
                os.getenv("SALES_ACTION_TOKEN", ""),
                "autoevolve-publisher-connections-v1",
            ]
        )
    digest = hashlib.sha256(material.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def init_publishers_db() -> None:
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS publisher_connections (
                org_id INTEGER NOT NULL,
                provider TEXT NOT NULL,
                url TEXT NOT NULL,
                account TEXT NOT NULL,
                label TEXT NOT NULL,
                platforms_json TEXT NOT NULL,
                secret_ciphertext TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (org_id, provider),
                FOREIGN KEY(org_id) REFERENCES buffer_orgs(id)
            );
            """
        )


def _platforms(value: list[str] | str | None) -> list[str]:
    if isinstance(value, str):
        parts = value.split(",")
    else:
        parts = value or list(DEFAULT_PLATFORMS)
    cleaned = []
    for part in parts:
        item = str(part).strip().lower()
        if item and item not in cleaned:
            cleaned.append(item)
    return cleaned or list(DEFAULT_PLATFORMS)


def save_webhook(
    org_id: int,
    *,
    url: str,
    secret: str,
    account: str = "webhook",
    label: str = "Webhook scheduler",
    platforms: list[str] | str | None = None,
) -> dict[str, Any]:
    if int(org_id) <= 0:
        raise ValueError("an active organization is required")
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("webhook URL must be an absolute http(s) URL")
    if len(secret.strip()) < 16:
        raise ValueError("webhook secret must be at least 16 characters")
    init_publishers_db()
    timestamp = now_iso()
    values = (
        int(org_id),
        "webhook",
        url.strip(),
        account.strip() or "webhook",
        label.strip() or "Webhook scheduler",
        json.dumps(_platforms(platforms)),
        _fernet().encrypt(secret.strip().encode("utf-8")).decode("ascii"),
        timestamp,
        timestamp,
    )
    with connect() as db:
        db.execute(
            "INSERT INTO publisher_connections "
            "(org_id, provider, url, account, label, platforms_json, secret_ciphertext, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(org_id, provider) DO UPDATE SET "
            "url=excluded.url, account=excluded.account, label=excluded.label, "
            "platforms_json=excluded.platforms_json, secret_ciphertext=excluded.secret_ciphertext, "
            "updated_at=excluded.updated_at",
            values,
        )
    return webhook_for_org(org_id) or {}


def webhook_for_org(org_id: int) -> dict[str, Any] | None:
    if int(org_id) <= 0:
        return None
    init_publishers_db()
    with connect() as db:
        row = db.execute(
            "SELECT * FROM publisher_connections WHERE org_id = ? AND provider = 'webhook'",
            (int(org_id),),
        ).fetchone()
    if not row:
        return None
    try:
        secret = _fernet().decrypt(row["secret_ciphertext"].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return None
    try:
        platforms = json.loads(row["platforms_json"])
    except ValueError:
        platforms = list(DEFAULT_PLATFORMS)
    return {
        "org_id": int(row["org_id"]),
        "provider": "webhook",
        "url": row["url"],
        "secret": secret,
        "account": row["account"],
        "label": row["label"],
        "platforms": tuple(platforms) if isinstance(platforms, list) else DEFAULT_PLATFORMS,
        "updated_at": row["updated_at"],
    }


def public_webhook_for_org(org_id: int) -> dict[str, Any] | None:
    connection = webhook_for_org(org_id)
    if not connection:
        return None
    return {
        key: value
        for key, value in connection.items()
        if key != "secret"
    } | {"configured": True, "secret_set": True}


def delete_webhook(org_id: int) -> None:
    if int(org_id) <= 0:
        return
    init_publishers_db()
    with connect() as db:
        db.execute(
            "DELETE FROM publisher_connections WHERE org_id = ? AND provider = 'webhook'",
            (int(org_id),),
        )
