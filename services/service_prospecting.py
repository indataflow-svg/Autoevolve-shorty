"""Credit-bounded, preview-only contact searches for a described service."""

from __future__ import annotations

import os
from typing import Any

from core.sales_store import list_leads, normalize_company_domain, upsert_lead
from core.state import claim_service_provider_request
from services.apollo import ApolloClient
from services.lusha import LushaClient
from services.prospeo import ProspeoClient, ProspeoError


def _cap(name: str, default: int) -> int:
    try:
        return min(max(int(os.getenv(name, str(default))), 0), 100)
    except ValueError:
        return default


def _identity(person: dict, company: dict, provider: str) -> dict | None:
    if provider == "apollo":
        name = person.get("name") or " ".join(filter(None, [person.get("first_name"), person.get("last_name")]))
        title = person.get("title")
        organization = person.get("organization") if isinstance(person.get("organization"), dict) else company
        company_name = organization.get("name") or person.get("organization_name")
        domain = organization.get("primary_domain") or person.get("organization_domain")
        country = organization.get("country") or person.get("country")
        person_id = person.get("person_id") or person.get("id")
    elif provider == "prospeo":
        name = person.get("full_name") or " ".join(filter(None, [person.get("first_name"), person.get("last_name")]))
        title = person.get("current_job_title") or person.get("headline")
        company_name = company.get("name")
        domain = company.get("website") or company.get("domain")
        location = person.get("location") if isinstance(person.get("location"), dict) else {}
        country = location.get("country") or person.get("country")
        person_id = person.get("person_id")
    else:
        name = " ".join(filter(None, [person.get("firstName"), person.get("lastName")]))
        job = person.get("jobTitle") if isinstance(person.get("jobTitle"), dict) else {}
        title = job.get("title") or person.get("headline")
        company_name = company.get("name")
        domain = company.get("domain")
        location = company.get("location") if isinstance(company.get("location"), dict) else {}
        country = location.get("country") or person.get("country")
        person_id = person.get("id")
    name = str(name or "").strip()
    company_name = str(company_name or "").strip()
    if not name or not company_name:
        return None
    return {
        "full_name": name, "job_title": str(title or "").strip() or None,
        "company": company_name, "company_domain": normalize_company_domain(domain),
        "country": str(country or "").strip() or None,
        "source": provider, "person_id": str(person_id or "").strip() or None,
    }


def _unique_key(item: dict) -> tuple[str, str]:
    company = normalize_company_domain(item.get("company_domain")) or str(item.get("company") or "").casefold()
    return (str(item["full_name"]).casefold(), company)


def _apollo_previews(keywords: list[str], buyer_titles: list[str], market: str | None, limit: int) -> list[dict]:
    rows = ApolloClient().people_service_search(
        keywords=keywords, job_titles=buyer_titles, location=market, limit=limit,
    )
    previews = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = _identity(row, {}, "apollo")
        if item:
            previews.append(item)
    return previews


def _prospeo_previews(keywords: list[str], buyer_titles: list[str], market: str | None, warnings: list[str]) -> list[dict]:
    client = ProspeoClient()
    filters: dict[str, Any] = {
        "person_job_title": {"include": buyer_titles[:3], "match_mode": "CONTAINS"},
        "company_keywords": {"include": keywords[:5], "include_all": False, "search_everywhere": True},
    }
    if market:
        try:
            suggestions = client.search_suggestions(location=market).get("location_suggestions") or []
            canonical = next(
                (item.get("name") for item in suggestions
                 if isinstance(item, dict) and str(item.get("name") or "").casefold() == market.casefold()),
                None,
            )
            if canonical:
                filters["company_location_search"] = {"include": [canonical]}
            else:
                warnings.append(f"Prospeo could not apply market '{market}' as a supported location; its results may be outside this market. Choose a country or city to narrow the search.")
        except ProspeoError:
            warnings.append(f"Prospeo could not validate market '{market}'; its results may be outside this market.")
    try:
        payload = client.search_person(filters, page=1)
    except ProspeoError as exc:
        if exc.error_code == "NO_RESULTS":
            warnings.append("Prospeo found no contacts for these keywords and titles. Edit the targeting and search again.")
            return []
        raise
    rows = payload.get("results") if isinstance(payload.get("results"), list) else payload.get("people") if isinstance(payload.get("people"), list) else []
    previews = []
    for row in rows[:25]:
        if not isinstance(row, dict):
            continue
        person = row.get("person") if isinstance(row.get("person"), dict) else row
        company = row.get("company") if isinstance(row.get("company"), dict) else person.get("company") if isinstance(person.get("company"), dict) else {}
        item = _identity(person, company, "prospeo")
        if item:
            previews.append(item)
    return previews


def _lusha_previews(keywords: list[str], buyer_titles: list[str], market: str | None, limit: int) -> list[dict]:
    payload = LushaClient().prospect_contacts(
        job_title=buyer_titles[0], service_keywords=keywords[:5], location=market,
        company_size=None, limit=limit,
    )
    rows = payload.get("results") if isinstance(payload.get("results"), list) else payload.get("contacts") if isinstance(payload.get("contacts"), list) else []
    previews = []
    for row in rows[:limit]:
        if not isinstance(row, dict):
            continue
        company = row.get("company") if isinstance(row.get("company"), dict) else {}
        item = _identity(row, company, "lusha")
        if item:
            previews.append(item)
    return previews


def _save_previews(previews: list[dict]) -> list[dict]:
    existing = {}
    for lead in list_leads(limit=1000):
        if not lead.get("full_name") or (lead.get("metadata") or {}).get("company_candidate"):
            continue
        existing[_unique_key(lead)] = lead
    saved = []
    for preview in previews:
        key = _unique_key(preview)
        lead = existing.get(key)
        if lead and lead.get("stage") == "suppressed":
            continue
        if not lead:
            provider = preview["source"]
            lead, _ = upsert_lead({
                **{field: preview[field] for field in ("full_name", "job_title", "company", "company_domain", "country", "source")},
                "source_detail": "service_discovery_preview",
                "metadata": {"service_discovery_preview": True, f"{provider}_person_id": preview.get("person_id")},
            })
            existing[key] = lead
        saved.append(lead)
    return saved


def search_service_contacts(
    *, keywords: list[str], buyer_titles: list[str], market: str | None, desired_contacts: int,
) -> dict[str, Any]:
    """Search providers once each, then save at most the requested contact previews."""
    if not 1 <= desired_contacts <= 25 or not keywords or not buyer_titles:
        raise ValueError("provide 1-25 contacts, search keywords, and buyer titles")
    previews: list[dict] = []
    providers: dict[str, int] = {}
    warnings: list[str] = []
    completed_providers: list[str] = []
    suppressed = {
        _unique_key(lead) for lead in list_leads(limit=1000)
        if lead.get("full_name") and lead.get("stage") == "suppressed"
    }

    def add(provider: str, fetch) -> None:
        try:
            rows = fetch()
            providers[provider] = len(rows)
            completed_providers.append(provider)
            previews.extend(item for item in rows if _unique_key(item) not in suppressed)
        except Exception as exc:
            providers[provider] = 0
            status = getattr(exc, "status", None)
            warnings.append(f"{provider} search unavailable ({status or type(exc).__name__})")

    if os.getenv("APOLLO_API_KEY"):
        if claim_service_provider_request("apollo", "people_search", _cap("SERVICE_APOLLO_PREVIEW_CAP_24H", 20)):
            add("apollo", lambda: _apollo_previews(keywords, buyer_titles, market, desired_contacts))
        else:
            warnings.append("apollo local 24-hour search cap reached")
    if len({_unique_key(item) for item in previews}) < desired_contacts and os.getenv("PROSPEO_API_KEY"):
        if claim_service_provider_request("prospeo", "people_search", _cap("SERVICE_PROSPEO_PREVIEW_CAP_24H", 1)):
            add("prospeo", lambda: _prospeo_previews(keywords, buyer_titles, market, warnings))
        else:
            warnings.append("prospeo local 24-hour search cap reached")
    if len({_unique_key(item) for item in previews}) < desired_contacts and os.getenv("LUSHA_API_KEY"):
        if claim_service_provider_request("lusha", "people_search", _cap("SERVICE_LUSHA_PREVIEW_CAP_24H", 0)):
            add("lusha", lambda: _lusha_previews(keywords, buyer_titles, market, desired_contacts))
        else:
            warnings.append("lusha preview disabled or local 24-hour cap reached")
    if not providers and not warnings:
        warnings.append("Configure Apollo or Prospeo prospecting keys to search contacts")

    unique: list[dict] = []
    seen = set()
    for item in previews:
        key = _unique_key(item)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
        if len(unique) >= desired_contacts:
            break
    saved = _save_previews(unique)
    return {"results": saved, "providers": providers, "completed_providers": completed_providers, "warnings": warnings}
