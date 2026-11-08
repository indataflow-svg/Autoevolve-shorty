"""GLEIF free entity resolution: step zero of the enrichment ladder.

The Global LEI Index (api.gleif.org) is free, keyless, and carries ~2.5M
legal entities with jurisdiction, status, and parent links. It answers "is
this a real company, where is it registered, who owns it" at zero cost —
before any paid Hunter/Apollo/Lusha/CompanyEnrich call fires.

Honesty rules (same as the rest of the ladder):
- GLEIF has no domains, only legal names. A hit is a *candidate*
  (`identity_confidence: "candidate-name-match"`), never a verified truth.
- Misses and transport errors return None so the caller falls through to
  the paid ladder silently. GLEIF never fails a resolution by itself.
- One best-effort direct-parent fetch enriches "sell into the group" plays;
  its failure never fails the identity.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

BASE_URL = "https://api.gleif.org/api/v1"
TIMEOUT_SECONDS = 15
PAGE_SIZE = 5


class GleifError(RuntimeError):
    pass


def _get_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.api+json"}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8")
            parsed = json.loads(raw) if raw else {}
            return parsed if isinstance(parsed, dict) else {}
    except urllib.error.HTTPError as exc:
        raise GleifError(f"GET {url} status={exc.code}") from exc
    except (TimeoutError, urllib.error.URLError, ValueError) as exc:
        raise GleifError(f"GET {url} transport_error={exc}") from exc


def search_records(company_name: str, *, page_size: int = PAGE_SIZE) -> list[dict[str, Any]]:
    """Full-text legal-name search. Raw JSON:API records, may be empty."""
    name = (company_name or "").strip()
    if not name:
        return []
    query = urllib.parse.urlencode(
        {"filter[entity.legalName]": name, "page[size]": max(1, min(page_size, 20))}
    )
    payload = _get_json(f"{BASE_URL}/lei-records?{query}")
    data = payload.get("data")
    return [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []


def _text(value: Any) -> str | None:
    if isinstance(value, dict):
        value = value.get("name", "")
    text = " ".join(str(value or "").split()).strip()
    return text or None


def extract_identity(record: dict[str, Any]) -> dict[str, Any]:
    """Flatten one lei-record into the identity dict the ladder stores."""
    attributes = record.get("attributes") if isinstance(record.get("attributes"), dict) else {}
    entity = attributes.get("entity") if isinstance(attributes.get("entity"), dict) else {}
    legal_address = entity.get("legalAddress") if isinstance(entity.get("legalAddress"), dict) else {}
    registration = attributes.get("registration") if isinstance(attributes.get("registration"), dict) else {}
    relationships = record.get("relationships") if isinstance(record.get("relationships"), dict) else {}
    direct_parent = relationships.get("direct-parent") if isinstance(relationships.get("direct-parent"), dict) else {}
    parent_links = direct_parent.get("links") if isinstance(direct_parent.get("links"), dict) else {}
    return {
        "lei": attributes.get("lei") or record.get("id"),
        "legal_name": _text((entity.get("legalName") or {}).get("name")),
        "jurisdiction": _text(entity.get("legalJurisdiction")),
        "country": _text(legal_address.get("country")),
        "city": _text(legal_address.get("city")),
        "entity_status": _text(entity.get("status")),
        "registration_status": _text(registration.get("status")),
        "managing_lou": _text(registration.get("managingLou")),
        "direct_parent_url": parent_links.get("related"),
        "identity_confidence": "candidate-name-match",
        "source": "gleif",
    }


def fetch_direct_parent(identity: dict[str, Any]) -> dict[str, Any] | None:
    """Best-effort direct-parent legalName/LEI. None on any failure."""
    url = identity.get("direct_parent_url")
    if not isinstance(url, str) or not url:
        return None
    try:
        payload = _get_json(url)
    except GleifError:
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    attributes = data.get("attributes") if isinstance(data.get("attributes"), dict) else {}
    entity = attributes.get("entity") if isinstance(attributes.get("entity"), dict) else {}
    name = _text((entity.get("legalName") or {}).get("name"))
    lei = attributes.get("lei") or data.get("id")
    if not name and not lei:
        return None
    return {"lei": lei, "legal_name": name}


def _prefer_active(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not records:
        return None
    for record in records:
        attributes = record.get("attributes") if isinstance(record.get("attributes"), dict) else {}
        entity = attributes.get("entity") if isinstance(attributes.get("entity"), dict) else {}
        if str(entity.get("status") or "").upper() == "ACTIVE":
            return record
    return records[0]


def resolve_identity(company_name: str) -> dict[str, Any] | None:
    """Free identity for a company name, or None (miss/error → paid ladder).

    Pure lookup: no writes, no side effects, no exceptions to the caller.
    """
    try:
        record = _prefer_active(search_records(company_name))
    except GleifError:
        return None
    if record is None:
        return None
    identity = extract_identity(record)
    if not identity.get("lei"):
        return None
    try:
        parent = fetch_direct_parent(identity)
    except Exception:
        parent = None
    identity["direct_parent"] = parent
    identity.pop("direct_parent_url", None)
    return identity
