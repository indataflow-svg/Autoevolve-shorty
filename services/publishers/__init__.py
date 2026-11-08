"""Publisher registry.

Buffer is always available and remains the default. The signed webhook
publisher appears only when PUBLISHER_WEBHOOK_URL and
PUBLISHER_WEBHOOK_SECRET are configured, so an unconfigured deployment does
not offer a dead option in the UI.
"""
from __future__ import annotations

from .base import Publisher, PublisherAccount, PublisherCapabilities, PublisherError
from .buffer import BufferPublisher
from .webhook import WebhookPublisher, load_config as load_webhook_config


_BUFFER = BufferPublisher()
_WEBHOOK = WebhookPublisher()


def get_publisher(name: str | None = None) -> Publisher:
    key = (name or "buffer").strip().lower()
    if key == "buffer":
        return _BUFFER
    if key == "webhook":
        return _WEBHOOK
    raise PublisherError(f"unknown publisher: {key}", 404)


def webhook_configured(org_id: int | None = None) -> bool:
    return load_webhook_config(org_id).configured


def _effective_org(org_id: int | None) -> int:
    if org_id is not None:
        return int(org_id)
    from core.auth_context import current_org_id

    return int(current_org_id.get() or 0)


def list_publishers(org_id: int | None = None) -> list[Publisher]:
    effective = _effective_org(org_id)
    publishers: list[Publisher] = []
    if effective:
        from core.state import get_org

        org = get_org(effective)
        # Free tenants never inherit the operator's global Buffer account.
        if org and (org.get("plan") or "paid") != "free":
            publishers.append(_BUFFER)
    else:
        publishers.append(_BUFFER)
    if webhook_configured(effective or None):
        publishers.append(_WEBHOOK)
    return publishers


def capabilities_dict(publisher: Publisher) -> dict:
    caps = publisher.capabilities()
    return {
        "draft": caps.draft,
        "schedule": caps.schedule,
        "confirm": caps.confirm,
        "insights": caps.insights,
        "platforms": list(caps.platforms),
    }


def catalog(org_id: int | None = None) -> list[dict]:
    return [
        {
            "name": publisher.name,
            "label": publisher.label,
            "capabilities": capabilities_dict(publisher),
        }
        for publisher in list_publishers(org_id)
    ]


__all__ = [
    "Publisher",
    "PublisherAccount",
    "PublisherCapabilities",
    "PublisherError",
    "get_publisher",
    "list_publishers",
    "catalog",
    "capabilities_dict",
    "webhook_configured",
]
