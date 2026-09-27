"""Typed, read-only contact views over the existing sales lead store."""

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from core.sales_store import get_lead, list_contacts_page

router = APIRouter(prefix="/company/sales/contacts", tags=["contacts"])

Stage = Literal[
    "new", "enriched", "qualified", "draft_ready", "approved", "contacted",
    "scheduled", "replied", "won", "lost", "suppressed",
]
Sort = Literal["recent", "oldest", "name", "score", "company"]


class ContactProfile(BaseModel):
    status: str
    email: str | None = None
    phone: str | None = None
    linkedin_url: str | None = None
    email_ready: bool
    ready_for_outreach: bool
    verification_status: str | None = None


class Contact(BaseModel):
    id: str
    full_name: str | None = None
    email: str | None = None
    job_title: str | None = None
    company: str | None = None
    company_domain: str | None = None
    phone: str | None = None
    country: str | None = None
    source: str
    source_detail: str | None = None
    message: str | None = None
    verification_status: str | None = None
    lead_score: int
    stage: Stage
    suppression_reason: str | None = None
    created_at: str
    updated_at: str
    last_touch_at: str | None = None
    contact_profile: ContactProfile


class ContactMetrics(BaseModel):
    total: int
    ready: int
    verified: int
    suppressed: int
    by_stage: dict[str, int]


class ContactsPage(BaseModel):
    items: list[Contact]
    total: int
    page: int
    page_size: int
    metrics: ContactMetrics


class CompanyProfile(BaseModel):
    domain: str
    company_name: str | None = None
    provider: str
    status: str
    summary: dict[str, Any]
    fetched_at: str | None = None


class DraftSummary(BaseModel):
    id: str
    subject: str
    status: str
    created_at: str


class InteractionSummary(BaseModel):
    id: int
    direction: str
    channel: str
    kind: str
    subject: str | None = None
    created_at: str


class EventSummary(BaseModel):
    id: int
    event: str
    created_at: str


class ContactDetail(Contact):
    metadata: dict[str, Any]
    company_profile: CompanyProfile | None = None
    drafts: list[DraftSummary]
    interactions: list[InteractionSummary]
    recent_events: list[EventSummary]


@router.get("", response_model=ContactsPage)
def contacts(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    stage: Stage | None = None,
    q: str = Query(default="", max_length=200),
    sort: Sort = "recent",
):
    items, total, metrics = list_contacts_page(
        page=page, page_size=page_size, stage=stage, query=q.strip(), sort=sort,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size, "metrics": metrics}


@router.get("/{contact_id}", response_model=ContactDetail)
def contact(contact_id: str):
    value = get_lead(contact_id)
    if value is None:
        raise HTTPException(404, "contact not found")
    value["last_touch_at"] = (value.get("latest_interaction") or {}).get("created_at")
    return value
