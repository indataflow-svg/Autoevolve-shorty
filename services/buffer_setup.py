"""Guided Buffer account setup.

One Buffer token is enough to read every organization and channel it can
publish to. The setup flow is therefore: pick (or name) an account, supply the
token once, discover the channels, then bind the Instagram/X channel IDs. The
per-channel values are identifiers, not extra secrets.

Nothing here returns the token. Writes go through ``core.setup_keys.write_values``
so they are backed up and rolled back on failure.
"""

from __future__ import annotations

import os
import re
from typing import Any, Callable

from core.setup_keys import g3_env_file, read_values, write_values

DEFAULT_ACCOUNT = "default"
ACCOUNT_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,30}$")

# Buffer's channel ``service`` -> the platform name G3 can publish to.
SERVICE_TO_PLATFORM = {
    "instagram": "instagram",
    "twitter": "x",
    "x": "x",
}
PLATFORMS = ("instagram", "x")

ClientFactory = Callable[[str], Any]


def normalize_account_name(value: str | None) -> str:
    name = str(value or DEFAULT_ACCOUNT).strip().lower()
    if not ACCOUNT_NAME_RE.fullmatch(name):
        raise ValueError("account name must use lowercase letters, digits, - or _ (max 31 characters)")
    return name


def account_keys(name: str) -> dict[str, str]:
    """Environment key names for one account, matching G3's prefix rules."""
    prefix = "BUFFER_" if name == DEFAULT_ACCOUNT else f"BUFFER_{name.upper().replace('-', '_')}_"
    return {
        "api_key": f"{prefix}API_KEY",
        "organization_id": f"{prefix}ORGANIZATION_ID",
        "instagram_channel_id": f"{prefix}INSTAGRAM_CHANNEL_ID",
        "x_channel_id": f"{prefix}X_CHANNEL_ID",
    }


def _values() -> dict[str, str]:
    """g3.env is the source of truth; process env fills deploy-time gaps."""
    values = dict(read_values(g3_env_file()))
    for key, value in os.environ.items():
        values.setdefault(key, value)
    return values


def list_accounts() -> list[dict]:
    """Configured accounts with masked state. Never returns the token."""
    values = _values()
    names = [DEFAULT_ACCOUNT] if values.get("BUFFER_API_KEY", "").strip() else []
    for key in values:
        if not key.startswith("BUFFER_") or not key.endswith("_API_KEY"):
            continue
        middle = key[len("BUFFER_") : -len("_API_KEY")]
        if not middle:
            continue
        name = middle.lower().replace("_", "-")
        if (
            ACCOUNT_NAME_RE.fullmatch(name)
            and name not in names
            and values.get(key, "").strip()
        ):
            names.append(name)
    accounts = []
    for name in sorted(names):
        keys = account_keys(name)
        accounts.append(
            {
                "name": name,
                "api_key_present": bool(values.get(keys["api_key"], "").strip()),
                "organization_id": values.get(keys["organization_id"], "").strip() or None,
                "instagram_channel_id": values.get(keys["instagram_channel_id"], "").strip() or None,
                "x_channel_id": values.get(keys["x_channel_id"], "").strip() or None,
            }
        )
    return accounts


def _resolve_api_key(account: str, provided: str | None) -> str:
    token = (provided or "").strip()
    if token:
        return token
    token = _values().get(account_keys(account)["api_key"], "").strip()
    if not token:
        raise ValueError(f"no saved API key for account {account!r}; enter one")
    return token


def _default_client(api_key: str) -> Any:
    from engines.g3.g3_runtime.buffer import BufferClient

    return BufferClient(
        api_key,
        os.getenv("BUFFER_API_ENDPOINT", "https://api.buffer.com"),
    )


def _text(value: Any) -> str:
    return str(value or "").strip()


def _channel(item: dict, service: str) -> dict:
    platform = SERVICE_TO_PLATFORM.get(service)
    return {
        "id": _text(item.get("id")),
        "name": _text(item.get("name")) or _text(item.get("displayName")),
        "display_name": _text(item.get("displayName")) or _text(item.get("name")),
        "descriptor": _text(item.get("descriptor")),
        "service": service,
        "type": _text(item.get("type")),
        "platform": platform,
        "supported": platform is not None,
        "usable": not bool(item.get("isDisconnected")) and not bool(item.get("isLocked")),
    }


def discover(
    account: str,
    api_key: str | None = None,
    *,
    client_factory: ClientFactory | None = None,
) -> dict:
    """Read the organizations and channels a token can reach.

    Read-only: no env write and no post. Raises ``ValueError`` for user-fixable
    input problems and lets provider errors propagate to the route.
    """
    name = normalize_account_name(account)
    token = _resolve_api_key(name, api_key)
    client = (client_factory or _default_client)(token)
    identity = client.account()
    organizations = []
    for raw_org in identity.get("organizations") or []:
        if not isinstance(raw_org, dict):
            continue
        org_id = _text(raw_org.get("id"))
        if not org_id:
            continue
        channels = []
        for raw_channel in client.channels(org_id) or []:
            if not isinstance(raw_channel, dict) or not _text(raw_channel.get("id")):
                continue
            service = _text(raw_channel.get("service")).lower()
            channels.append(_channel(raw_channel, service))
        organizations.append(
            {
                "id": org_id,
                "name": _text(raw_org.get("name")) or org_id,
                "channels": channels,
            }
        )
    if not organizations:
        raise ValueError("this Buffer token has no organizations")
    return {
        "account": name,
        "account_id": _text(identity.get("id")),
        "organizations": organizations,
    }


def bind(
    account: str,
    *,
    api_key: str | None,
    organization_id: str,
    instagram_channel_id: str | None = None,
    x_channel_id: str | None = None,
    client_factory: ClientFactory | None = None,
) -> dict:
    """Verify the chosen channel IDs against Buffer, then persist the account."""
    name = normalize_account_name(account)
    token = _resolve_api_key(name, api_key)
    if len(token) < 8 or any(ch.isspace() for ch in token):
        raise ValueError("API key looks invalid")
    org_id = (organization_id or "").strip()
    if not org_id:
        raise ValueError("organization_id is required")

    # Re-discover with the token being saved so a channel from another account
    # (or another organization) can never be bound by mistake.
    found = discover(name, token, client_factory=client_factory)
    organization = next((org for org in found["organizations"] if org["id"] == org_id), None)
    if organization is None:
        raise ValueError("organization does not belong to this API key")
    usable = {
        channel["id"]: channel
        for channel in organization["channels"]
        if channel["usable"] and channel["supported"]
    }

    requested = {
        "instagram": (instagram_channel_id or "").strip(),
        "x": (x_channel_id or "").strip(),
    }
    chosen: dict[str, str] = {}
    for platform, channel_id in requested.items():
        if not channel_id:
            chosen[platform] = ""
            continue
        channel = usable.get(channel_id)
        if channel is None:
            raise ValueError(f"{platform} channel is not a usable channel in this organization")
        if channel["platform"] != platform:
            raise ValueError(f"channel {channel_id!r} is {channel['platform']}, not {platform}")
        chosen[platform] = channel_id

    warnings = []
    if not any(chosen.values()):
        warnings.append("No Instagram or X channel was bound; this account cannot schedule yet.")
    unsupported = sorted(
        {
            channel["service"]
            for channel in organization["channels"]
            if not channel["supported"] and channel["service"]
        }
    )
    if unsupported:
        warnings.append(
            "Unsupported services were left unbound: " + ", ".join(unsupported) + "."
        )

    keys = account_keys(name)
    values = {
        keys["api_key"]: token,
        keys["organization_id"]: org_id,
        keys["instagram_channel_id"]: chosen["instagram"],
        keys["x_channel_id"]: chosen["x"],
    }
    written = write_values(g3_env_file(), values)
    if not written.get("ok"):
        raise ValueError(written.get("error") or "could not write the Buffer configuration")

    # G3 subprocesses read g3.env per command; this keeps the in-process account
    # list consistent immediately instead of showing stale state until restart.
    for key, value in values.items():
        os.environ[key] = value

    return {
        "ok": True,
        "account": name,
        "organization_id": org_id,
        "instagram_channel_id": chosen["instagram"] or None,
        "x_channel_id": chosen["x"] or None,
        "warnings": warnings,
        "saved": written["saved"],
        "backup": written.get("backup"),
        "restart_required": False,
    }
