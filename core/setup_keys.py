"""Setup key management: grouped provider keys with test-before-save.

Writes go to the repo .env (root keys) or engines/g3/config/g3.env
(Buffer/R2 keys), always with a timestamped .bak first and rollback
on validation failure. Reads are masked: values never leave the server.
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV_FILE = ROOT / ".env"
DEFAULT_G3_ENV_FILE = ROOT / "engines" / "g3" / "config" / "g3.env"

# Overridable in tests via SETUP_ENV_FILE / SETUP_G3_ENV_FILE.
ENV_FILE = Path(os.getenv("SETUP_ENV_FILE", str(DEFAULT_ENV_FILE)))
G3_ENV_FILE = Path(os.getenv("SETUP_G3_ENV_FILE", str(DEFAULT_G3_ENV_FILE)))

SECRET_HINTS = ("KEY", "TOKEN", "SECRET", "PASSWORD")


def env_file() -> Path:
    return Path(os.getenv("SETUP_ENV_FILE", str(DEFAULT_ENV_FILE)))


def g3_env_file() -> Path:
    return Path(os.getenv("SETUP_G3_ENV_FILE", str(DEFAULT_G3_ENV_FILE)))


# group -> {file, keys}. Order matches the setup wizard cards.
PROVIDER_GROUPS: dict[str, dict] = {
    "ai_gateway": {
        "file": "env",
        "label": "AI gateway",
        "keys": [
            "OMNIROUTE_BASE_URL",
            "OMNIROUTE_API_KEY",
            "MODEL_FAST",
            "MODEL_REASONING",
            "MODEL_FREE",
            "MODEL_CODING",
            "MODEL_VISION",
            "CODING_BASE_URL",
            "CODING_API_KEY",
            "CODING_DEFAULT_MODEL",
        ],
    },
    "prospecting": {
        "file": "env",
        "label": "Prospecting + enrichment",
        "keys": [
            "PROSPEO_API_KEY",
            "LUSHA_API_KEY",
            "HUNTER_API_KEY",
            "APOLLO_API_KEY",
            "PDL_API_KEY",
            "CE_API_KEY",
        ],
    },
    "email": {
        "file": "env",
        "label": "Outbound email",
        "keys": [
            "SALES_RESEND_API_KEY",
            "SALES_RESEND_DOMAIN",
            "SALES_FROM_NAME",
            "SALES_FROM_EMAIL",
            "SALES_REPLY_TO_EMAIL",
            "SALES_RESEND_WEBHOOK_SECRET",
        ],
    },
    "media": {
        "file": "env",
        "label": "Stock media",
        "keys": [
            "PEXELS_API_KEY",
            "PIXABAY_API_KEY",
            "COVERR_API_KEY",
            "LORDICON_API_TOKEN",
            "OMNIROUTE_IMAGE_MODEL",
        ],
    },
    "social": {
        "file": "g3env",
        "label": "Buffer + R2 publishing",
        "keys": [
            "BUFFER_API_KEY",
            "BUFFER_ORGANIZATION_ID",
            "BUFFER_INSTAGRAM_CHANNEL_ID",
            "BUFFER_X_CHANNEL_ID",
            "R2_ACCOUNT_ID",
            "R2_ACCESS_KEY_ID",
            "R2_SECRET_ACCESS_KEY",
            "R2_BUCKET",
            "R2_PUBLIC_BASE_URL",
        ],
    },
    "forms": {
        "file": "env",
        "label": "Forms + attribution",
        "keys": [
            "TALLY_API_KEY",
            "TALLY_WEBHOOK_SECRET",
            "MARKETING_CTA_URL",
            "MARKETING_FORMS_BASE_URL",
        ],
    },
}


def _read_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        if key:
            values[key] = value.strip().strip('"').strip("'")
    return values


def group_status() -> dict[str, dict]:
    """Masked per-group status: which keys are set (never values)."""
    env_values = _read_values(env_file())
    g3_values = _read_values(g3_env_file())
    status: dict[str, dict] = {}
    for group, spec in PROVIDER_GROUPS.items():
        source = g3_values if spec["file"] == "g3env" else env_values
        keys = spec["keys"]
        configured = [k for k in keys if source.get(k, "").strip()]
        status[group] = {
            "label": spec["label"],
            "file": str(g3_env_file() if spec["file"] == "g3env" else env_file()),
            "configured": configured,
            "missing": [k for k in keys if k not in configured],
            "ready": bool(configured),
        }
    return status


def _is_secret_key(name: str) -> bool:
    upper = name.upper()
    return any(hint in upper for hint in SECRET_HINTS)


def validate_group(group: str, values: dict[str, str]) -> dict:
    """Format-level validation (no credits spent). Live gateway check for ai_gateway."""
    if group not in PROVIDER_GROUPS:
        return {"ok": False, "error": f"unknown group: {group}"}
    errors: dict[str, str] = {}
    cleaned = {k: (v or "").strip() for k, v in values.items() if k in PROVIDER_GROUPS[group]["keys"]}
    for key, value in cleaned.items():
        if not value:
            continue
        if " " in value or "\n" in value:
            errors[key] = "must not contain spaces or newlines"
        elif _is_secret_key(key) and len(value) < 8 and value != "ollama":
            errors[key] = "looks too short for a key"
    if group == "email" and cleaned.get("SALES_FROM_EMAIL") and cleaned.get("SALES_RESEND_DOMAIN"):
        domain = cleaned["SALES_RESEND_DOMAIN"].lower()
        sender = cleaned["SALES_FROM_EMAIL"].lower()
        if not sender.endswith("@" + domain) and not sender.endswith("." + domain):
            errors["SALES_FROM_EMAIL"] = f"sender domain must match verified domain {domain}"
    if errors:
        return {"ok": False, "errors": errors}
    if group == "ai_gateway":
        live = _test_ai_gateway(cleaned)
        if not live["ok"]:
            return live
    return {"ok": True, "checked": sorted(cleaned)}


def _test_ai_gateway(values: dict[str, str]) -> dict:
    """Live check against the user-supplied gateway URL (no credits beyond /models)."""
    import httpx

    base_url = (values.get("OMNIROUTE_BASE_URL") or "").rstrip("/") or None
    api_key = (values.get("OMNIROUTE_API_KEY") or "").strip()
    if base_url and not api_key:
        return {"ok": False, "errors": {"OMNIROUTE_API_KEY": "key is required when a base URL is set"}}
    if api_key and not base_url:
        return {"ok": False, "errors": {"OMNIROUTE_BASE_URL": "base URL is required when a key is set"}}
    if not base_url:
        return {"ok": True, "checked": []}
    try:
        response = httpx.get(
            f"{base_url}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )
    except Exception as exc:
        return {"ok": False, "errors": {"OMNIROUTE_BASE_URL": f"unreachable: {type(exc).__name__}: {exc}"}}
    if response.status_code == 401:
        return {"ok": False, "errors": {"OMNIROUTE_API_KEY": "gateway rejected the key (401)"}}
    if response.status_code >= 400:
        return {"ok": False, "errors": {"OMNIROUTE_BASE_URL": f"gateway returned HTTP {response.status_code}"}}
    return {"ok": True, "checked": ["OMNIROUTE_BASE_URL", "OMNIROUTE_API_KEY"]}


def _backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = path.with_name(f"{path.name}.{stamp}.bak")
    shutil.copy2(path, backup)
    _prune_backups(path)
    return backup


def _prune_backups(path: Path, keep: int = 5) -> None:
    backups = sorted(path.parent.glob(f"{path.name}.*.bak"))
    for old in backups[:-keep] if len(backups) > keep else []:
        try:
            old.unlink()
        except OSError:
            pass


def save_group(group: str, values: dict[str, str]) -> dict:
    """Validate, backup, then write. Rolls back the file on any failure."""
    if group not in PROVIDER_GROUPS:
        return {"ok": False, "error": f"unknown group: {group}"}
    spec = PROVIDER_GROUPS[group]
    cleaned = {k: (v or "").strip() for k, v in values.items() if k in spec["keys"]}
    validation = validate_group(group, cleaned)
    if not validation.get("ok"):
        return validation
    path = g3_env_file() if spec["file"] == "g3env" else env_file()
    if not path.exists():
        return {"ok": False, "error": f"env file not found: {path} (run make init first)"}
    original = path.read_bytes()
    backup = _backup(path)
    try:
        lines = path.read_text().splitlines()
        seen: set[str] = set()
        updated: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key = stripped.partition("=")[0].strip()
                if key in cleaned:
                    updated.append(f"{key}={cleaned[key]}")
                    seen.add(key)
                    continue
            updated.append(line)
        for key in spec["keys"]:
            if key in cleaned and key not in seen:
                updated.append(f"{key}={cleaned[key]}")
        path.write_text("\n".join(updated) + "\n")
    except Exception as exc:
        try:
            path.write_bytes(original)
        except OSError:
            pass
        return {"ok": False, "error": f"write failed, rolled back: {exc}"}
    return {
        "ok": True,
        "group": group,
        "saved": sorted(cleaned),
        "backup": str(backup) if backup else None,
        "restart_required": True,
    }
