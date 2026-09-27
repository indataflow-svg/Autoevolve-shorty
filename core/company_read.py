"""Read-only company projections over existing sales leads and profile cache.

Domains are the only shared company identity in the sales store. A lead with a
company name but no domain stays separate to avoid merging unrelated firms.
"""

from __future__ import annotations

import json
from typing import Any

from core.sales_store import connect, normalize_company_domain


SUMMARY_FIELDS = (
    "id", "name", "domain", "identity_kind", "industry", "size", "country",
    "source", "lead_count", "contact_count", "candidate", "profile_status",
    "last_seen_at", "representative_lead_id", "candidate_lead_id", "has_profile",
)


def _text(value: Any) -> str | None:
    cleaned = str(value).strip() if value is not None else ""
    return cleaned or None


def _summary_value(summary: dict[str, Any], key: str) -> str | None:
    value = summary.get(key)
    return _text(value) if isinstance(value, (str, int, float)) else None


def _strings(value: Any) -> list[str]:
    return [item.strip() for item in value if isinstance(item, str) and item.strip()] if isinstance(value, list) else []


def _collect() -> dict[str, dict[str, Any]]:
    companies: dict[str, dict[str, Any]] = {}

    def bucket(company_id: str, *, domain: str | None, name: str | None) -> dict[str, Any]:
        if company_id not in companies:
            companies[company_id] = {
                "id": company_id, "name": name or domain or "Unnamed company",
                "domain": domain, "identity_kind": "domain" if domain else "lead",
                "industry": None, "size": None, "country": None, "source": None,
                "lead_count": 0, "contact_count": 0, "candidate": False,
                "profile_status": None, "last_seen_at": None,
                "representative_lead_id": None, "candidate_lead_id": None,
                "has_profile": False, "description": None, "website": None,
                "linkedin_url": None, "technologies": [], "specialties": [],
                "summary_line": None, "profile_provider": None,
                "profile_fetched_at": None, "contacts": [],
            }
        return companies[company_id]

    with connect() as connection:
        profiles = connection.execute(
            "SELECT domain, company_name, provider, status, summary_json, fetched_at, updated_at "
            "FROM sales_company_profiles"
        ).fetchall()
        leads = connection.execute(
            "SELECT id, full_name, job_title, email, company, company_domain, country, "
            "source, stage, updated_at, metadata_json FROM sales_leads "
            "WHERE company IS NOT NULL OR company_domain IS NOT NULL "
            "ORDER BY updated_at DESC, id DESC"
        ).fetchall()

    for row in profiles:
        domain = normalize_company_domain(row["domain"])
        if not domain:
            continue
        raw_summary = json.loads(row["summary_json"] or "{}")
        summary = raw_summary if isinstance(raw_summary, dict) else {}
        location = summary.get("location") if isinstance(summary.get("location"), dict) else {}
        signals = summary.get("signals") if isinstance(summary.get("signals"), dict) else {}
        item = bucket(f"domain:{domain}", domain=domain, name=_text(row["company_name"]) or _summary_value(summary, "name"))
        item.update({
            "industry": _summary_value(summary, "industry"),
            "size": _summary_value(summary, "employee_range") or _summary_value(summary, "employee_count"),
            "country": _text(location.get("country")),
            "profile_status": _text(row["status"]),
            "last_seen_at": row["updated_at"],
            "has_profile": True,
            "description": _summary_value(summary, "description"),
            "website": _summary_value(summary, "website"),
            "linkedin_url": _summary_value(summary, "linkedin_url"),
            "technologies": _strings(summary.get("technologies")),
            "specialties": _strings(summary.get("specialties")),
            "summary_line": _text(signals.get("summary_line")),
            "profile_provider": _text(row["provider"]),
            "profile_fetched_at": row["fetched_at"],
        })

    for row in leads:
        domain = normalize_company_domain(row["company_domain"])
        company_name = _text(row["company"])
        if not domain and not company_name:
            continue
        company_id = f"domain:{domain}" if domain else f"lead:{row['id']}"
        item = bucket(company_id, domain=domain, name=company_name)
        if not item["has_profile"] and company_name:
            item["name"] = company_name
        item["lead_count"] += 1
        item["source"] = item["source"] or row["source"]
        item["country"] = item["country"] or row["country"]
        item["last_seen_at"] = max(filter(None, (item["last_seen_at"], row["updated_at"])), default=None)
        item["representative_lead_id"] = item["representative_lead_id"] or row["id"]
        metadata = json.loads(row["metadata_json"] or "{}")
        is_candidate = isinstance(metadata, dict) and metadata.get("company_candidate") is True
        if is_candidate:
            item["candidate"] = True
            item["candidate_lead_id"] = item["candidate_lead_id"] or row["id"]
            item["representative_lead_id"] = item["candidate_lead_id"]
        elif row["email"] or row["job_title"] or (row["full_name"] and row["full_name"] != row["company"]):
            item["contacts"].append({
                "id": row["id"], "full_name": row["full_name"],
                "job_title": row["job_title"], "email": row["email"],
                "stage": row["stage"],
            })
            item["contact_count"] += 1

    return companies


def list_company_records(
    *, page: int, page_size: int, query: str, view: str, sort: str,
    industry: str = "", country: str = "",
) -> tuple[list[dict[str, Any]], int, dict[str, int]]:
    values = list(_collect().values())
    metrics = {
        "total": len(values),
        "candidates": sum(bool(item["candidate"]) for item in values),
        "profiled": sum(bool(item["has_profile"]) for item in values),
        "with_contacts": sum(item["contact_count"] > 0 for item in values),
    }
    needle = query.strip().casefold()
    if needle:
        values = [item for item in values if any(
            needle in str(item.get(key) or "").casefold()
            for key in ("name", "domain", "industry", "country", "source")
        )]
    if industry.strip():
        values = [item for item in values if industry.strip().casefold() in str(item["industry"] or "").casefold()]
    if country.strip():
        values = [item for item in values if country.strip().casefold() in str(item["country"] or "").casefold()]
    if view == "candidates":
        values = [item for item in values if item["candidate"]]
    elif view == "profiled":
        values = [item for item in values if item["has_profile"]]
    elif view == "with_contacts":
        values = [item for item in values if item["contact_count"] > 0]
    if sort == "name":
        values.sort(key=lambda item: (item["name"].casefold(), item["id"]))
    elif sort == "contacts":
        values.sort(key=lambda item: (-item["contact_count"], item["name"].casefold()))
    else:
        values.sort(key=lambda item: (item["last_seen_at"] or "", item["id"]), reverse=True)
    total = len(values)
    slice_ = values[(page - 1) * page_size:page * page_size]
    return [{key: item[key] for key in SUMMARY_FIELDS} for item in slice_], total, metrics


def get_company_record(company_id: str) -> dict[str, Any] | None:
    item = _collect().get(company_id)
    return dict(item) if item else None
