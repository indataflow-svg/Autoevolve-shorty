from __future__ import annotations

import os
import re
from dataclasses import dataclass

from .errors import G3Error


ACCOUNT_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,30}$")
DEFAULT_ACCOUNT = "default"


@dataclass(frozen=True)
class BufferAccount:
    name: str
    api_key: str
    organization_id: str
    instagram_channel_id: str
    x_channel_id: str

    def channel_for(self, platform: str) -> str:
        if platform == "x":
            value = self.x_channel_id
        else:
            value = self.instagram_channel_id
        if not value:
            raise G3Error(f"buffer account {self.name!r} has no channel configured for {platform!r}")
        return value

    def describe(self) -> dict:
        return {
            "name": self.name,
            "organization_id": self.organization_id or None,
            "instagram_channel_id": bool(self.instagram_channel_id),
            "x_channel_id": bool(self.x_channel_id),
        }


def normalize_account_name(value: str | None) -> str:
    name = str(value or DEFAULT_ACCOUNT).strip().lower()
    if not ACCOUNT_NAME_RE.fullmatch(name):
        raise G3Error(f"invalid buffer account name {value!r}: use lowercase letters, digits, - or _")
    return name


def _prefix(name: str) -> str:
    if name == DEFAULT_ACCOUNT:
        return "BUFFER_"
    return f"BUFFER_{name.upper().replace('-', '_')}_"


def load_account(name: str | None = None) -> BufferAccount:
    """Resolve one named Buffer account from the environment.

    The default account uses the unprefixed variables (BUFFER_API_KEY, ...).
    Extra accounts use prefixed variables, e.g. BUFFER_ACME_API_KEY,
    BUFFER_ACME_ORGANIZATION_ID, BUFFER_ACME_INSTAGRAM_CHANNEL_ID,
    BUFFER_ACME_X_CHANNEL_ID. Keys live in engines/g3/config/g3.env.
    """
    resolved = normalize_account_name(name)
    prefix = _prefix(resolved)
    get = lambda suffix: os.environ.get(prefix + suffix, "").strip()
    api_key = get("API_KEY")
    if not api_key:
        hint = "BUFFER_API_KEY" if resolved == DEFAULT_ACCOUNT else f"{prefix}API_KEY"
        raise G3Error(
            f"buffer account {resolved!r} is not configured: set {hint} "
            f"(get a token at publish.buffer.com/account/api, see docs/keys.md)"
        )
    return BufferAccount(
        name=resolved,
        api_key=api_key,
        organization_id=get("ORGANIZATION_ID"),
        instagram_channel_id=get("INSTAGRAM_CHANNEL_ID"),
        x_channel_id=get("X_CHANNEL_ID"),
    )


def list_accounts() -> list[dict]:
    """Names of every account with an API key present (keys never leave here)."""
    names = [DEFAULT_ACCOUNT] if os.environ.get("BUFFER_API_KEY", "").strip() else []
    for key in os.environ:
        if not key.startswith("BUFFER_") or not key.endswith("_API_KEY"):
            continue
        middle = key[len("BUFFER_"):-len("_API_KEY")]
        if not middle or middle in {"API"}:
            continue
        name = middle.lower().replace("_", "-")
        if ACCOUNT_NAME_RE.fullmatch(name) and name not in names and os.environ.get(key, "").strip():
            names.append(name)
    described = []
    for name in sorted(names):
        try:
            described.append(load_account(name).describe())
        except G3Error:
            described.append({"name": name, "organization_id": None,
                              "instagram_channel_id": False, "x_channel_id": False})
    return described
