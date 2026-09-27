"""Typed company views over the existing prospect and enrichment records."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from core.company_read import get_company_record, list_company_records

router = APIRouter(prefix="/company/sales/companies", tags=["companies"])

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
        industry=industry, country=country,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size, "metrics": metrics}


@router.get("/{company_id:path}", response_model=CompanyDetail)
def company(company_id: str):
    value = get_company_record(company_id)
    if value is None:
        raise HTTPException(404, "company not found")
    return value
