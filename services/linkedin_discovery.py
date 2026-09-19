"""LinkedIn profile discovery for sales leads.

Resolves a lead to a LinkedIn profile URL using the prospecting providers
already configured (Apollo first, Prospeo second). Read-only enrichment:
no messages are sent, nothing is automated. Results are stored in the
lead's ``contact_resolution.details`` so the founder can copy-paste
manual outreach from the dashboard.
"""

from __future__ import annotations

from typing import Any

from core.sales_store import add_event, get_lead, merge_lead_metadata
from services.apollo import ApolloClient, ApolloError
from services.prospeo import ProspeoClient, ProspeoError


def _clean_url(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if "linkedin.com" not in text.lower():
        return None
    if not text.startswith(("http://", "https://")):
        text = f"https://{text}"
    return text


def _apollo_discover(lead: dict[str, Any]) -> str | None:
    client = ApolloClient()
    email = lead.get("email")
    name = lead.get("full_name")
    domain = lead.get("company_domain")
    if not (email or name or domain):
        return None
    person = client.match_person(email=email, name=name, domain=domain)
    url = _clean_url(person.get("linkedin_url"))
    if url:
        return url
    if not domain:
        return None
    for candidate in client.people_search(domain, limit=10):
        if not isinstance(candidate, dict):
            continue
        if name and candidate.get("name") and name.lower() not in str(candidate.get("name")).lower():
            continue
        url = _clean_url(candidate.get("linkedin_url"))
        if url:
            return url
    return None


def _prospeo_discover(lead: dict[str, Any]) -> str | None:
    client = ProspeoClient()
    metadata = lead.get("metadata") if isinstance(lead.get("metadata"), dict) else {}
    person_id = metadata.get("prospeo_person_id")
    if person_id:
        person = client.enrich_person(str(person_id))
        url = _clean_url(person.get("linkedin_url"))
        if url:
            return url
    filters: dict[str, Any] = {}
    if lead.get("full_name"):
        filters["full_name"] = lead.get("full_name")
    if lead.get("company"):
        filters["company_name"] = lead.get("company")
    if lead.get("company_domain"):
        filters["company_domain"] = lead.get("company_domain")
    if not filters:
        return None
    payload = client.search_person(filters)
    for key in ("persons", "people", "results", "data", "profiles"):
        items = payload.get(key)
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    url = _clean_url(item.get("linkedin_url"))
                    if url:
                        return url
    return None


_PROVIDERS = ("apollo", "prospeo")


def discover_linkedin(lead_id: str, provider: str = "auto", force: bool = False) -> dict[str, Any]:
    """Find and store a lead's LinkedIn profile URL.

    provider: "auto" (apollo, then prospeo), "apollo", or "prospeo".
    Returns {"ok", "cached", "provider", "status", "linkedin_url", "lead"}.
    status is "resolved" (URL found), "missing" (providers answered, no URL),
    or raises ValueError/502-style RuntimeError on failure.
    """
    lead = get_lead(lead_id)
    if not lead:
        raise ValueError("lead not found")
    if lead.get("stage") == "suppressed":
        raise ValueError("suppressed leads cannot be enriched")
    metadata = lead.get("metadata") if isinstance(lead.get("metadata"), dict) else {}
    resolution = metadata.get("contact_resolution") if isinstance(metadata.get("contact_resolution"), dict) else {}
    details = resolution.get("details") if isinstance(resolution.get("details"), dict) else {}
    cached = _clean_url(details.get("linkedin_url"))
    if cached and not force:
        return {
            "ok": True,
            "cached": True,
            "provider": str(details.get("linkedin_provider") or "cache"),
            "status": "resolved",
            "linkedin_url": cached,
            "lead": lead,
        }
    chosen = (provider or "auto").strip().lower()
    if chosen != "auto" and chosen not in _PROVIDERS:
        raise ValueError("linkedin discovery provider must be auto, apollo, or prospeo")
    ordered = _PROVIDERS if chosen == "auto" else (chosen,)
    errors: list[str] = []
    for name in ordered:
        try:
            url = _apollo_discover(lead) if name == "apollo" else _prospeo_discover(lead)
        except (ApolloError, ProspeoError) as exc:
            errors.append(f"{name}: {exc}")
            continue
        if url:
            updated = merge_lead_metadata(lead_id, {
                "contact_resolution": {
                    "details": {
                        **details,
                        "linkedin_url": url,
                        "linkedin_provider": name,
                    }
                }
            })
            add_event(lead_id, "linkedin.discovered", {"provider": name, "linkedin_url": url})
            return {
                "ok": True,
                "cached": False,
                "provider": name,
                "status": "resolved",
                "linkedin_url": url,
                "lead": get_lead(lead_id) or updated,
            }
    if errors and not cached:
        raise RuntimeError(f"linkedin discovery failed: {'; '.join(errors)}")
    updated = merge_lead_metadata(lead_id, {
        "contact_resolution": {
            "details": {
                **details,
                "linkedin_url": None,
                "linkedin_provider": ordered[-1],
            }
        }
    })
    add_event(lead_id, "linkedin.missing", {"providers": list(ordered)})
    return {
        "ok": True,
        "cached": False,
        "provider": ordered[-1],
        "status": "missing",
        "linkedin_url": None,
        "lead": get_lead(lead_id) or updated,
    }
