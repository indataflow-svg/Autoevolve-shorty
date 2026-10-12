"""Typed, read-only operational views for the React integrations/settings pages."""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter
from pydantic import BaseModel

from core.branding import company_forms_url, company_public_url
from core.setup_keys import PROVIDER_GROUPS, group_status
from core.state import VALID_CAPABILITIES, get_active_org, get_org_capabilities, list_orgs

router = APIRouter(prefix="/company/ui", tags=["workspace"])


class SessionStatus(BaseModel):
    authenticated: bool


@router.get("/session", response_model=SessionStatus)
def session_status():
    """Validate dashboard Basic credentials without reading a product domain."""
    return {"authenticated": True}

GROUP_CATEGORIES = {
    "ai_gateway": "AI", "prospecting": "Lead data", "email": "Email",
    "media": "Media", "social": "Publishing", "forms": "Forms",
}
GROUP_CAPABILITIES = {
    "ai_gateway": ["Model routing", "Coding"],
    "prospecting": ["Prospecting", "Enrichment"],
    "email": ["Outbound email", "Inbound replies"],
    "media": ["Stock media", "Image generation"],
    "social": ["Buffer drafts", "Media hosting"],
    "forms": ["Lead capture", "Attribution"],
}


class ConnectionSummary(BaseModel):
    """A canonical connection row, sans secrets. The registry owns state;
    this endpoint only projects it next to key presence so the two views
    cannot disagree about whether an organization is connected."""

    provider: str
    status: str
    sync_status: str
    last_sync_at: str | None = None


class ProviderGroup(BaseModel):
    id: str
    label: str
    category: str
    capabilities: list[str]
    configured_keys: list[str]
    missing_keys: list[str]
    configured_count: int
    total_keys: int
    connections: list[ConnectionSummary] = []


class IntegrationsView(BaseModel):
    groups: list[ProviderGroup]
    total_groups: int
    groups_with_configuration: int
    fully_configured_groups: int
    configured_keys: int
    connected_providers: int = 0


@router.get("/integrations", response_model=IntegrationsView)
def integrations_view():
    status = group_status()
    summaries, key_of = _org_connections()
    groups = []
    for group_id, spec in PROVIDER_GROUPS.items():
        current = status[group_id]
        configured = current["configured"]
        missing = current["missing"]
        groups.append({
            "id": group_id, "label": spec["label"],
            "category": GROUP_CATEGORIES[group_id],
            "capabilities": GROUP_CAPABILITIES[group_id],
            "configured_keys": configured, "missing_keys": missing,
            "configured_count": len(configured), "total_keys": len(spec["keys"]),
            "connections": [s for s in summaries if key_of.get(s["provider"]) in spec["keys"]],
        })
    orphans = [s for s in summaries
               if not any(key_of.get(s["provider"]) in spec["keys"]
                          for spec in PROVIDER_GROUPS.values())]
    if orphans:
        groups.append({
            "id": "connected_accounts", "label": "Connected accounts",
            "category": "Connections",
            "capabilities": ["Organization connections"],
            "configured_keys": [], "missing_keys": [],
            "configured_count": 0, "total_keys": 0,
            "connections": orphans,
        })
    return {
        "groups": groups,
        "total_groups": len(groups),
        "groups_with_configuration": sum(bool(group["configured_count"]) for group in groups),
        "fully_configured_groups": sum(not group["missing_keys"] for group in groups),
        "configured_keys": sum(group["configured_count"] for group in groups),
        "connected_providers": sum(
            1 for s in summaries if s["status"] in ("healthy", "connected")),
    }


def _org_connections() -> tuple[list[dict], dict[str, str]]:
    """Project the canonical registry next to key presence.

    Key presence answers "are credentials configured"; only the registry
    answers "is this organization connected". Reading both here keeps the
    workspace page and the commercial catalog consistent by construction.
    Returns (connection summaries, provider -> credential-key map); the map
    is a join key only and never leaves this module.
    """
    from core import commercial_store

    try:
        org = commercial_store.active_org_id()
    except Exception:
        return [], {}
    summaries: list[dict] = []
    key_of: dict[str, str] = {}
    for row in commercial_store._list("integration_connections", org, 100):
        if row.get("status") == "disconnected":
            continue
        summaries.append({
            "provider": row["provider"],
            "status": row.get("status") or "disconnected",
            "sync_status": row.get("sync_status") or "idle",
            "last_sync_at": row.get("last_sync_at"),
        })
        key_of[row["provider"]] = row.get("credential_ref") or ""
    return summaries, key_of


class WorkspaceOrg(BaseModel):
    id: int
    name: str
    slug: str
    domain: str
    status: str | None = None
    capabilities: dict[str, bool]


class PublicLink(BaseModel):
    id: Literal["app", "forms", "calendar"]
    label: str
    url: str | None
    state: Literal["local", "placeholder", "configured", "invalid"]


class SettingsView(BaseModel):
    orgs: list[WorkspaceOrg]
    active_org_id: int | None
    available_capabilities: list[str]
    public_links: list[PublicLink]


def _public_link(link_id: str, label: str, raw: str) -> dict:
    parsed = urlsplit(raw.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        return {"id": link_id, "label": label, "url": None, "state": "invalid"}
    # Query strings and fragments can contain tokens, so never include them in this view.
    safe_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
    host = parsed.hostname.lower()
    if host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"} or host.endswith(".local"):
        state = "local"
    elif host == "example.com" or host.endswith(".example.com") or host.endswith(".example"):
        state = "placeholder"
    else:
        state = "configured"  # Configuration only; reachability is not asserted.
    return {"id": link_id, "label": label, "url": safe_url, "state": state}


@router.get("/settings", response_model=SettingsView)
def settings_view():
    from app.api import _calendar_booking_url

    active = get_active_org()
    orgs = [
        {"id": org["id"], "name": org["name"], "slug": org["slug"],
         "domain": org.get("domain") or "", "status": org.get("status"),
         "capabilities": get_org_capabilities(org["id"])}
        for org in list_orgs()
    ]
    return {
        "orgs": orgs,
        "active_org_id": active["id"] if active else None,
        "available_capabilities": list(VALID_CAPABILITIES),
        "public_links": [
            _public_link("app", "AutoEvolve app", company_public_url()),
            _public_link("forms", "Lead forms", company_forms_url()),
            _public_link("calendar", "Booking calendar", _calendar_booking_url()),
        ],
    }
