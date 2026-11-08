"""Typed company views over the existing prospect and enrichment records."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from core.company_read import get_company_record, list_company_records
from services import gleif as gleif_service

router = APIRouter(prefix="/company/sales/companies", tags=["companies"])


def _org() -> int:
    from core.state import get_active_org

    active = get_active_org()
    return int(active["id"]) if active else 0

CompanyView = Literal["all", "candidates", "profiled", "with_contacts"]
CompanySort = Literal["recent", "name", "contacts"]


class CompanyContact(BaseModel):
    id: str
    full_name: str | None = None
    job_title: str | None = None
    email: str | None = None
    stage: str


class CompanySummary(BaseModel):
    id: str
    name: str
    domain: str | None = None
    identity_kind: Literal["domain", "lead"]
    industry: str | None = None
    size: str | None = None
    country: str | None = None
    source: str | None = None
    lead_count: int
    contact_count: int
    candidate: bool
    profile_status: str | None = None
    last_seen_at: str | None = None
    representative_lead_id: str | None = None
    candidate_lead_id: str | None = None
    has_profile: bool


class CompanyMetrics(BaseModel):
    total: int
    candidates: int
    profiled: int
    with_contacts: int


class CompaniesPage(BaseModel):
    items: list[CompanySummary]
    total: int
    page: int
    page_size: int
    metrics: CompanyMetrics


class CompanyDetail(CompanySummary):
    description: str | None = None
    website: str | None = None
    linkedin_url: str | None = None
    technologies: list[str]
    specialties: list[str]
    summary_line: str | None = None
    profile_provider: str | None = None
    profile_fetched_at: str | None = None
    contacts: list[CompanyContact]


@router.get("", response_model=CompaniesPage)
def companies(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    q: str = Query(default="", max_length=200),
    industry: str = Query(default="", max_length=100),
    country: str = Query(default="", max_length=100),
    view: CompanyView = "all",
    sort: CompanySort = "recent",
):
    items, total, metrics = list_company_records(
        page=page, page_size=page_size, query=q, view=view, sort=sort,
        industry=industry, country=country, org_id=_org(),
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size, "metrics": metrics}


class CompanyVerification(BaseModel):
    domain: str | None = None
    gleif: dict | None = None
    web_presence: dict | None = None
    cached_profile: bool = False


@router.get("/verify/lookup", response_model=CompanyVerification)
def verify_company(
    domain: str = Query(default="", max_length=253),
    name: str = Query(default="", max_length=200),
):
    """Free verification state for a prospect company. Read-only, no writes.

    GLEIF is looked up live (free, keyless); web presence and enriched
    profiles come from local stores only. A miss in any source is reported,
    never filled — the calibration UI renders it as an honest badge.
    """
    from core import worlddata_store
    from core.sales_store import get_company_profile

    clean_domain = domain.strip().lower().split("/")[0] or None
    clean_name = name.strip() or None
    gleif: dict | None = None
    if clean_name:
        try:
            identity = gleif_service.resolve_identity(clean_name)
        except Exception:
            identity = None
        if identity:
            gleif = {
                "legal_name": identity.get("legal_name"),
                "lei": identity.get("lei"),
                "country": identity.get("country"),
                "status": identity.get("entity_status"),
                "confidence": identity.get("identity_confidence"),
            }
    web_presence: dict | None = None
    if clean_domain:
        record = worlddata_store.get_record("commoncrawl", "web_presence", clean_domain)
        if record:
            data = record.get("data") or {}
            web_presence = {
                "captures": data.get("captures"),
                "first_seen": data.get("first_seen"),
                "last_seen": data.get("last_seen"),
                "vintage": record.get("vintage"),
            }
    cached = False
    if clean_domain:
        try:
            profile = get_company_profile(clean_domain, org_id=_org())
            cached = bool(profile) and profile.get("status") == "resolved"
        except Exception:
            cached = False
    return {"domain": clean_domain, "gleif": gleif,
            "web_presence": web_presence, "cached_profile": cached}


@router.get("/{company_id:path}", response_model=CompanyDetail)
def company(company_id: str):
    value = get_company_record(company_id, org_id=_org())
    if value is None:
        raise HTTPException(404, "company not found")
    return value
