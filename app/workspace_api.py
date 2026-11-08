"""Typed, read-only operational views for the React integrations/settings pages."""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.branding import company_forms_url, company_public_url
from core.setup_keys import PROVIDER_GROUPS, group_status
from app.sales_api import verify_founder_action
from core.state import (
    VALID_CAPABILITIES,
    get_active_org,
    get_org,
    get_org_capabilities,
    get_org_limits,
    list_orgs,
    set_org_limits,
)

router = APIRouter(prefix="/company/ui", tags=["workspace"])


class SessionStatus(BaseModel):
    authenticated: bool


@router.get("/session", response_model=SessionStatus)
def session_status():
    """Validate dashboard Basic credentials without reading a product domain."""
    return {"authenticated": True}

GROUP_CATEGORIES = {
    "ai_gateway": "AI", "prospecting": "Lead data", "email": "Email",
    "media": "Media", "social": "Publishing", "media_hosting": "Publishing",
    "forms": "Forms",
}
GROUP_CAPABILITIES = {
    "ai_gateway": ["Model routing", "Coding"],
    "prospecting": ["Prospecting", "Enrichment"],
    "email": ["Outbound email", "Inbound replies"],
    "media": ["Stock media", "Image generation"],
    "social": ["Buffer drafts", "Scheduled posts"],
    "media_hosting": ["Media hosting for Buffer"],
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


class ProviderAccountSummary(BaseModel):
    """One named Buffer account, masked. Channels are the bound platforms."""

    name: str
    api_key_present: bool
    organization_id: str | None = None
    channels: list[str] = []


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
    accounts: list[ProviderAccountSummary] = []


class IntegrationsView(BaseModel):
    groups: list[ProviderGroup]
    total_groups: int
    groups_with_configuration: int
    fully_configured_groups: int
    configured_keys: int
    connected_providers: int = 0


@router.get("/integrations", response_model=IntegrationsView)
def integrations_view():
    from services.buffer_setup import list_accounts

    from core.auth_context import current_org_id

    status = group_status()
    summaries, key_of = _org_connections()
    scoped = current_org_id.get()
    scoped_org = get_org(int(scoped)) if scoped else None
    if scoped_org and scoped_org.get("plan") == "free":
        raise HTTPException(403, "provider setup is not available on the free plan")
    buffer_accounts = list_accounts()
    groups = []
    for group_id, spec in PROVIDER_GROUPS.items():
        current = status[group_id]
        configured = current["configured"]
        missing = current["missing"]
        accounts = []
        if group_id == "social":
            accounts = [
                {
                    "name": account["name"],
                    "api_key_present": account["api_key_present"],
                    "organization_id": account["organization_id"],
                    "channels": [
                        platform
                        for platform, key in (
                            ("instagram", "instagram_channel_id"),
                            ("x", "x_channel_id"),
                            ("linkedin", "linkedin_channel_id"),
                        )
                        if account[key]
                    ],
                }
                for account in buffer_accounts
            ]
        groups.append({
            "id": group_id, "label": spec["label"],
            "category": GROUP_CATEGORIES[group_id],
            "capabilities": GROUP_CAPABILITIES[group_id],
            "configured_keys": configured, "missing_keys": missing,
            "configured_count": len(configured), "total_keys": len(spec["keys"]),
            "connections": [s for s in summaries if key_of.get(s["provider"]) in spec["keys"]],
            "accounts": accounts,
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
        "groups_with_configuration": sum(
            bool(group["configured_count"]) or bool(group["accounts"]) for group in groups
        ),
        "fully_configured_groups": sum(
            (not group["missing_keys"])
            or any(account["channels"] for account in group["accounts"])
            for group in groups
        ),
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

    from core.auth_context import current_org_id

    active = get_active_org()
    scoped = current_org_id.get()
    visible = [get_org(int(scoped))] if scoped else list_orgs()
    orgs = [
        {"id": org["id"], "name": org["name"], "slug": org["slug"],
         "domain": org.get("domain") or "", "status": org.get("status"),
         "capabilities": get_org_capabilities(org["id"])}
        for org in visible if org
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


class GovernanceLimitsView(BaseModel):
    plan: str
    max_spend_usd: float
    max_actions: int
    max_outreach_contacts: int
    max_duration_days: int
    overrides: dict


class GovernanceLimitsPayload(BaseModel):
    max_spend_usd: float | None = None
    max_actions: int | None = None
    max_outreach_contacts: int | None = None
    max_duration_days: int | None = None


def _org_id() -> int:
    active = get_active_org()
    return int(active["id"]) if active else 0


@router.get("/limits", response_model=GovernanceLimitsView)
def limits_view():
    from core.plan_governance import GovernanceLimits

    org = _org_id()
    effective = GovernanceLimits.load(org)
    return {
        "plan": "free" if org == 0 else (get_active_org() or {}).get("plan", "paid"),
        **effective.model_dump(),
        "overrides": get_org_limits(org),
    }


@router.put("/limits", response_model=GovernanceLimitsView, dependencies=[Depends(verify_founder_action)])
def save_limits(payload: GovernanceLimitsPayload):
    from core.plan_governance import GovernanceLimits

    org = _org_id()
    if org == 0:
        raise HTTPException(409, "no active org")
    values = {key: value for key, value in payload.model_dump().items() if value is not None}
    try:
        set_org_limits(org, values)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    effective = GovernanceLimits.load(org)
    return {
        "plan": (get_active_org() or {}).get("plan", "paid"),
        **effective.model_dump(),
        "overrides": get_org_limits(org),
    }


class QuotaItem(BaseModel):
    kind: str
    plan: str
    used: int
    limit: int
    remaining: int
    reset_at: str


class QuotasView(BaseModel):
    plan: str
    quotas: dict[str, QuotaItem]


@router.get("/quotas", response_model=QuotasView)
def quotas_view():
    from core.quotas import quota_snapshot_all

    org = _org_id()
    return {
        "plan": (get_active_org() or {}).get("plan", "paid"),
        "quotas": quota_snapshot_all(org),
    }


class WebhookConnectionPayload(BaseModel):
    url: str
    secret: str
    account: str = "webhook"
    label: str = "Webhook scheduler"
    platforms: str = "instagram,x,linkedin"


@router.get("/publishers")
def publisher_connections_view():
    from core.publishers_store import public_webhook_for_org
    from services.publishers import catalog

    org = _org_id()
    return {
        "publishers": catalog(),
        "webhook": public_webhook_for_org(org),
    }


@router.put("/publishers/webhook", dependencies=[Depends(verify_founder_action)])
def save_webhook_connection(payload: WebhookConnectionPayload):
    from core.publishers_store import public_webhook_for_org, save_webhook

    org = _org_id()
    if org == 0:
        raise HTTPException(409, "no active org")
    try:
        save_webhook(
            org,
            url=payload.url,
            secret=payload.secret,
            account=payload.account,
            label=payload.label,
            platforms=payload.platforms,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"webhook": public_webhook_for_org(org)}


@router.delete("/publishers/webhook", dependencies=[Depends(verify_founder_action)])
def delete_webhook_connection():
    from core.publishers_store import delete_webhook

    org = _org_id()
    if org == 0:
        raise HTTPException(409, "no active org")
    delete_webhook(org)
    return {"webhook": None}
