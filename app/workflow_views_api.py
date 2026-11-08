"""Typed read projections for the modern workflow pages.

Writes remain owned by sales_api and marketing_api. These views never infer a
provider outcome, a publication, or a future scheduled action from a draft.
"""

from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from core import marketing_store, sales_store
from core.marketing_routing import RouteState, stored_route_state
from core.state import get_active_org, get_org

router = APIRouter(prefix="/company/ui", tags=["workflow-views"])


def _org() -> int:
    active = get_active_org()
    return int(active["id"]) if active else 0


def _org_condition(alias: str, org: int) -> str:
    return f"({alias}.org_id=? OR {alias}.org_id IS NULL)" if org == 0 else f"{alias}.org_id=?"


class ReplyItem(BaseModel):
    id: int
    lead_id: str
    company: str | None
    company_domain: str | None
    contact_name: str | None
    contact_role: str | None
    email: str | None
    lead_stage: str
    channel: str
    kind: str
    subject: str | None
    body: str | None
    answers: dict | None
    form_slug: str | None
    provider_message_id: str | None
    received_at: str
    is_latest_interaction: bool
    can_draft_reply: bool


class RepliesPage(BaseModel):
    items: list[ReplyItem]
    total: int
    page: int
    page_size: int
    counts: dict[str, int]


# Both inbound channels the page owns: email replies and form submissions.
# Nothing else (outbound, drafts, meeting invitations) is an inbound reply.
_REPLY_FROM = """FROM sales_interactions i JOIN sales_leads l ON l.id = i.lead_id
WHERE i.direction = 'inbound' AND (
    (i.channel = 'email' AND i.kind = 'reply')
    OR (i.channel = 'form' AND i.kind = 'submission')
)"""
_REPLY_SELECT = """SELECT i.id, i.lead_id, l.company, l.company_domain,
    l.full_name AS contact_name, l.job_title AS contact_role, l.email, l.stage AS lead_stage,
    i.channel, i.kind, i.subject, i.body,
    json_extract(i.metadata_json, '$.answers') AS answers,
    json_extract(i.metadata_json, '$.form_slug') AS form_slug,
    i.provider_message_id, i.created_at AS received_at,
    i.id = (SELECT newest.id FROM sales_interactions newest WHERE newest.lead_id = i.lead_id ORDER BY newest.created_at DESC LIMIT 1) AS is_latest_interaction"""


def _reply_item(row) -> dict:
    item = dict(row)
    item["is_latest_interaction"] = bool(item["is_latest_interaction"])
    item["answers"] = json.loads(item["answers"]) if item.get("answers") else None
    # A form submission has no email thread to answer into; drafting stays an
    # email-reply action.
    item["can_draft_reply"] = (
        item["is_latest_interaction"]
        and item["channel"] == "email"
        and item["lead_stage"] != "suppressed"
        and bool(item["email"])
    )
    return item


@router.get("/replies", response_model=RepliesPage)
def replies_view(
    page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=50),
    q: str = Query("", max_length=200), view: Literal["all", "latest", "submissions", "suppressed"] = "all",
    sort: Literal["recent", "oldest", "company"] = "recent",
):
    org = _org()
    conditions: list[str] = [_org_condition("l", org)]
    values: list[object] = [org]
    if view == "latest":
        conditions.append("i.id = (SELECT newest.id FROM sales_interactions newest WHERE newest.lead_id = i.lead_id ORDER BY newest.created_at DESC LIMIT 1)")
    elif view == "submissions":
        conditions.append("i.channel = 'form'")
    elif view == "suppressed":
        conditions.append("l.stage = 'suppressed'")
    if q.strip():
        escaped = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        conditions.append("(l.company LIKE ? ESCAPE '\\' OR l.full_name LIKE ? ESCAPE '\\' "
                          "OR i.subject LIKE ? ESCAPE '\\' OR i.body LIKE ? ESCAPE '\\')")
        values.extend([pattern] * 4)
    where = _REPLY_FROM + (" AND " + " AND ".join(conditions) if conditions else "")
    ordering = {"recent": "i.created_at DESC, i.id DESC", "oldest": "i.created_at ASC, i.id ASC",
                "company": "l.company COLLATE NOCASE ASC, i.created_at DESC, i.id DESC"}[sort]
    with sales_store.connect() as connection:
        total = connection.execute(f"SELECT COUNT(*) {where}", values).fetchone()[0]
        rows = connection.execute(
            f"{_REPLY_SELECT} {where} ORDER BY {ordering} LIMIT ? OFFSET ?",
            [*values, page_size, (page - 1) * page_size],
        ).fetchall()
        counts = connection.execute(f"""SELECT COUNT(*) AS total,
            SUM(CASE WHEN i.id = (SELECT newest.id FROM sales_interactions newest WHERE newest.lead_id = i.lead_id ORDER BY newest.created_at DESC LIMIT 1) THEN 1 ELSE 0 END) AS latest,
            SUM(CASE WHEN i.channel = 'form' THEN 1 ELSE 0 END) AS submissions,
            SUM(CASE WHEN l.stage = 'suppressed' THEN 1 ELSE 0 END) AS suppressed,
            SUM(CASE WHEN i.provider_message_id IS NOT NULL THEN 1 ELSE 0 END) AS threaded
            {_REPLY_FROM} AND {_org_condition("l", org)}""", (org,)).fetchone()
    return {"items": [_reply_item(row) for row in rows], "total": total, "page": page,
            "page_size": page_size, "counts": {key: counts[key] or 0 for key in counts.keys()}}


@router.get("/replies/{reply_id}", response_model=ReplyItem)
def reply_detail(reply_id: int):
    with sales_store.connect() as connection:
        org = _org()
        row = connection.execute(
            f"{_REPLY_SELECT} {_REPLY_FROM} AND {_org_condition('l', org)} AND i.id = ?",
            (org, reply_id),
        ).fetchone()
    if not row:
        raise HTTPException(404, "inbound reply not found")
    return _reply_item(row)


class MeetingMarker(BaseModel):
    id: str
    lead_id: str
    company: str | None
    company_domain: str | None
    contact_name: str | None
    contact_role: str | None
    email: str | None
    status: str
    scheduled_for: str | None
    slots: list[str] | None
    note: str | None
    recorded_at: str | None
    source: str | None


class MeetingsPage(BaseModel):
    items: list[MeetingMarker]
    total: int
    page: int
    page_size: int
    counts: dict[str, int]


# Both meeting states the page owns: a booked marker and a founder-sent
# booking request the contact has not answered yet.
_MEETING_FROM = """FROM sales_leads l
WHERE json_extract(l.metadata_json, '$.meeting.status') IN ('scheduled', 'awaiting_booking')"""
_MEETING_SELECT = """SELECT l.id, l.id AS lead_id, l.company, l.company_domain,
    l.full_name AS contact_name, l.job_title AS contact_role, l.email,
    json_extract(l.metadata_json, '$.meeting.status') AS status,
    json_extract(l.metadata_json, '$.meeting.scheduled_for') AS scheduled_for,
    json_extract(l.metadata_json, '$.meeting.slots') AS slots,
    json_extract(l.metadata_json, '$.meeting.note') AS note,
    json_extract(l.metadata_json, '$.meeting.updated_at') AS recorded_at,
    json_extract(l.metadata_json, '$.meeting.source') AS source"""


def _meeting_item(row) -> dict:
    item = dict(row)
    item["slots"] = json.loads(item["slots"]) if item.get("slots") else None
    return item


@router.get("/meetings", response_model=MeetingsPage)
def meetings_view(
    page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=50),
    q: str = Query("", max_length=200), view: Literal["all", "dated", "undated", "awaiting"] = "all",
    sort: Literal["recent", "oldest", "company"] = "recent",
):
    org = _org()
    conditions: list[str] = [_org_condition("l", org)]
    values: list[object] = [org]
    if view == "dated":
        conditions.append("json_extract(l.metadata_json, '$.meeting.scheduled_for') IS NOT NULL")
    elif view == "undated":
        conditions.append("json_extract(l.metadata_json, '$.meeting.scheduled_for') IS NULL")
    elif view == "awaiting":
        conditions.append("json_extract(l.metadata_json, '$.meeting.status') = 'awaiting_booking'")
    if q.strip():
        escaped = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        conditions.append("(l.company LIKE ? ESCAPE '\\' OR l.full_name LIKE ? ESCAPE '\\' OR l.email LIKE ? ESCAPE '\\')")
        values.extend([pattern] * 3)
    where = _MEETING_FROM + (" AND " + " AND ".join(conditions) if conditions else "")
    ordering = {"recent": "recorded_at DESC, l.id DESC", "oldest": "recorded_at ASC, l.id ASC",
                "company": "l.company COLLATE NOCASE ASC, l.id ASC"}[sort]
    with sales_store.connect() as connection:
        total = connection.execute(f"SELECT COUNT(*) {where}", values).fetchone()[0]
        rows = connection.execute(
            f"{_MEETING_SELECT} {where} ORDER BY {ordering} LIMIT ? OFFSET ?",
            [*values, page_size, (page - 1) * page_size],
        ).fetchall()
        counts = connection.execute(f"""SELECT COUNT(*) AS total,
            SUM(CASE WHEN json_extract(l.metadata_json, '$.meeting.scheduled_for') IS NOT NULL THEN 1 ELSE 0 END) AS dated,
            SUM(CASE WHEN json_extract(l.metadata_json, '$.meeting.scheduled_for') IS NULL THEN 1 ELSE 0 END) AS undated,
            SUM(CASE WHEN json_extract(l.metadata_json, '$.meeting.status') = 'awaiting_booking' THEN 1 ELSE 0 END) AS awaiting,
            SUM(CASE WHEN json_extract(l.metadata_json, '$.meeting.note') IS NOT NULL THEN 1 ELSE 0 END) AS with_note
            {_MEETING_FROM} AND {_org_condition("l", org)}""", (org,)).fetchone()
    return {"items": [_meeting_item(row) for row in rows], "total": total, "page": page,
            "page_size": page_size, "counts": {key: counts[key] or 0 for key in counts.keys()}}


@router.get("/meetings/{lead_id}", response_model=MeetingMarker)
def meeting_detail(lead_id: str):
    with sales_store.connect() as connection:
        org = _org()
        row = connection.execute(
            f"{_MEETING_SELECT} {_MEETING_FROM} AND {_org_condition('l', org)} AND l.id = ?",
            (org, lead_id),
        ).fetchone()
    if not row:
        raise HTTPException(404, "recorded meeting marker not found")
    return _meeting_item(row)


class OutreachItem(BaseModel):
    id: str
    lead_id: str
    company: str | None
    company_domain: str | None
    contact_name: str | None
    contact_role: str | None
    email: str | None
    channel: str
    kind: str
    status: str
    subject: str
    body: str
    in_reply_to: str | None
    created_at: str
    updated_at: str
    approved_at: str | None
    sent_at: str | None


class OutreachPage(BaseModel):
    items: list[OutreachItem]
    total: int
    page: int
    page_size: int
    by_status: dict[str, int]
    benchmark: dict | None = None


def _outreach_item(row) -> dict:
    value = dict(row)
    return {key: value.get(key) for key in OutreachItem.model_fields}


def _outreach_benchmark(approved: int) -> dict:
    """World-data expectation for the sendable approved batch. Read-only.

    A single draft's expectation rounds to noise, so the unit is the batch:
    N approved drafts at the world cold-reply band. Recorded reply rates
    (shown in workflow suggestions) take precedence once they exist.
    """
    from core import channel_benchmarks as benchmarks
    from core.suggest import _evidence_industry

    industry = _evidence_industry(0)
    return {
        "sendable": approved,
        "industry": industry,
        "expected": benchmarks.expected_replies(approved, industry),
        "cold": benchmarks.cold_reply_benchmark(industry),
    }


@router.get("/outreach", response_model=OutreachPage)
def outreach_view(
    page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=50),
    q: str = Query("", max_length=200), status: str = Query("", max_length=40),
    sort: Literal["recent", "oldest", "company"] = "recent",
):
    org = _org()
    where: list[str] = [_org_condition("l", org)]
    values: list[object] = [org]
    if status:
        where.append("d.status = ?")
        values.append(status)
    if q.strip():
        escaped = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        where.append("(l.company LIKE ? ESCAPE '\\' OR l.full_name LIKE ? ESCAPE '\\' OR "
                     "l.email LIKE ? ESCAPE '\\' OR d.subject LIKE ? ESCAPE '\\')")
        values.extend([pattern] * 4)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    ordering = {
        "recent": "d.updated_at DESC, d.id DESC",
        "oldest": "d.updated_at ASC, d.id ASC",
        "company": "l.company COLLATE NOCASE ASC, d.id ASC",
    }[sort]
    join = "FROM sales_drafts d JOIN sales_leads l ON l.id = d.lead_id"
    with sales_store.connect() as connection:
        total = connection.execute(f"SELECT COUNT(*) {join} {clause}", values).fetchone()[0]
        rows = connection.execute(
            "SELECT d.id, d.lead_id, l.company, l.company_domain, l.full_name AS contact_name, "
            "l.job_title AS contact_role, l.email, d.channel, d.kind, d.status, d.subject, d.body, "
            "d.in_reply_to, d.created_at, d.updated_at, d.approved_at, d.sent_at "
            f"{join} {clause} ORDER BY {ordering} LIMIT ? OFFSET ?",
            [*values, page_size, (page - 1) * page_size],
        ).fetchall()
        counts = connection.execute(
            "SELECT d.status, COUNT(*) AS count FROM sales_drafts d "
            "JOIN sales_leads l ON l.id = d.lead_id "
            f"WHERE {_org_condition('l', org)} GROUP BY d.status",
            (org,),
        ).fetchall()
    by_status = {row["status"]: row["count"] for row in counts}
    return {"items": [_outreach_item(row) for row in rows], "total": total, "page": page,
            "page_size": page_size, "by_status": by_status,
            "benchmark": _outreach_benchmark(by_status.get("approved", 0))}


@router.get("/outreach/{draft_id}", response_model=OutreachItem)
def outreach_detail(draft_id: str):
    org = _org()
    with sales_store.connect() as connection:
        row = connection.execute(
            "SELECT d.id, d.lead_id, l.company, l.company_domain, l.full_name AS contact_name, "
            "l.job_title AS contact_role, l.email, d.channel, d.kind, d.status, d.subject, d.body, "
            "d.in_reply_to, d.created_at, d.updated_at, d.approved_at, d.sent_at "
            "FROM sales_drafts d JOIN sales_leads l ON l.id = d.lead_id "
            f"WHERE {_org_condition('l', org)} AND d.id = ?", (org, draft_id),
        ).fetchone()
    if not row:
        raise HTTPException(404, "draft not found")
    return _outreach_item(row)


class ContentItem(BaseModel):
    id: str
    kind: Literal["manual_post"]
    title: str
    org_name: str | None
    format: str
    stage: str
    buffer_status: str | None
    caption: str | None
    platform: str | None
    publisher: str = "buffer"
    publisher_status: str | None = None
    publisher_post_ids: list[str] = Field(default_factory=list)
    publisher_account: str | None = None
    publisher_scheduled_at: str | None = None
    asset_count: int
    asset_urls: list[str]
    updated_at: str | None
    buffer_post_ids: list[str]
    buffer_accounts: list[str]
    buffer_scheduled_at: str | None
    preferred_buffer_account: str | None = None
    send_confirmation: dict | None = None


class ContentView(BaseModel):
    items: list[ContentItem]
    manual_posts_loaded: int
    manual_posts_truncated: bool


@router.get("/content", response_model=ContentView)
def content_view():
    from app.marketing_api import _manual_post_buffer_status, _manual_post_status

    org_id = _org()
    manual = marketing_store.list_manual_posts(limit=200, org_id=org_id)
    with marketing_store.connect() as connection:
        manual_total = connection.execute(
            "SELECT COUNT(*) FROM marketing_manual_posts WHERE org_id=?", (org_id,)
        ).fetchone()[0]
    items = []
    for post in manual:
        metadata = post.get("metadata") or {}
        org = get_org(post["org_id"])
        items.append({
            "id": post["id"], "kind": "manual_post", "title": post.get("title") or metadata.get("generated_title") or post["post_id"],
            "org_name": org["name"] if org else None, "format": metadata.get("post_type") or "manual post",
            "stage": _manual_post_status(post), "buffer_status": _manual_post_buffer_status(post),
            "caption": metadata.get("generated_caption") or post.get("creative"), "platform": post["platform"],
            "publisher": metadata.get("publisher") or "buffer",
            "publisher_status": metadata.get("publisher_status") or _manual_post_buffer_status(post),
            "publisher_post_ids": [str(value) for value in (metadata.get("publisher_post_ids") or metadata.get("buffer_post_ids") or []) if value],
            "publisher_account": metadata.get("publisher_account") or metadata.get("buffer_account"),
            "publisher_scheduled_at": metadata.get("publisher_scheduled_at") or metadata.get("buffer_scheduled_at"),
            "asset_count": len(post.get("assets") or []),
            "asset_urls": [f"/company/marketing/manual-posts/{post['id']}/assets/{index}" for index in range(len(post.get("assets") or []))],
            "updated_at": post["updated_at"],
            "buffer_post_ids": [str(value) for value in metadata.get("buffer_post_ids") or [] if value],
            "buffer_accounts": [str(value) for value in metadata.get("buffer_accounts") or [] if value],
            "buffer_scheduled_at": metadata.get("buffer_scheduled_at"),
            "preferred_buffer_account": metadata.get("preferred_buffer_account"),
            "send_confirmation": metadata.get("publisher_send_confirmation") or metadata.get("buffer_send_confirmation"),
        })
    items.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    return {"items": items, "manual_posts_loaded": len(manual),
            "manual_posts_truncated": manual_total > len(manual)}


class RecentContact(BaseModel):
    id: str
    full_name: str | None
    company: str | None
    stage: str
    updated_at: str


class HomeView(RouteState):
    contacts_total: int
    outreach_drafts_total: int
    outreach_approved_total: int
    outreach_unknown_total: int
    manual_posts_total: int
    active_org_name: str | None
    recent_contacts: list[RecentContact]
    drafts_waiting_approval: int
    latest_replies: int
    open_provider_incidents: int
    onboarding_ready: bool = False


@router.get("/home", response_model=HomeView)
def home_view():
    from core.ops_store import list_incidents
    from core.company_context import get_company_context

    active = get_active_org()
    org_id = int(active["id"]) if active else 0
    with sales_store.connect() as connection:
        contacts_total = connection.execute(
            "SELECT COUNT(*) FROM sales_leads WHERE org_id=?", (org_id,)
        ).fetchone()[0]
        draft_rows = connection.execute(
            "SELECT d.status, COUNT(*) AS count FROM sales_drafts d "
            "JOIN sales_leads l ON l.id = d.lead_id WHERE l.org_id=? GROUP BY d.status",
            (org_id,),
        ).fetchall()
        latest_replies = connection.execute("""SELECT COUNT(*) FROM sales_interactions i
            JOIN sales_leads l ON l.id = i.lead_id
            WHERE l.org_id=? AND i.direction = 'inbound' AND (
                (i.channel = 'email' AND i.kind = 'reply')
                OR (i.channel = 'form' AND i.kind = 'submission')
            )
            AND i.id = (SELECT newer.id FROM sales_interactions newer WHERE newer.lead_id = i.lead_id ORDER BY newer.created_at DESC, newer.id DESC LIMIT 1)""", (org_id,)).fetchone()[0]
        contact_rows = connection.execute(
            "SELECT id, full_name, company, stage, updated_at FROM sales_leads "
            "WHERE org_id=? ORDER BY updated_at DESC LIMIT 5", (org_id,)
        ).fetchall()
    draft_counts = {row["status"]: row["count"] for row in draft_rows}
    with marketing_store.connect() as connection:
        manual_posts_total = connection.execute(
            "SELECT COUNT(*) FROM marketing_manual_posts WHERE org_id=?", (org_id,)
        ).fetchone()[0]
    context = get_company_context(org_id)
    onboarding_ready = bool(context and context.workflow_ready)
    from core.auth_context import current_org_id

    incidents = [] if current_org_id.get() else list_incidents(limit=100)
    return {
        "contacts_total": contacts_total, "outreach_drafts_total": sum(draft_counts.values()),
        "outreach_approved_total": draft_counts.get("approved", 0),
        "outreach_unknown_total": draft_counts.get("send_unknown", 0),
        "manual_posts_total": manual_posts_total,
        "active_org_name": active["name"] if active else None,
        "recent_contacts": [dict(row) for row in contact_rows],
        "drafts_waiting_approval": draft_counts.get("draft", 0),
        "latest_replies": latest_replies,
        "open_provider_incidents": sum(1 for item in incidents if item and item["status"] not in {"resolved", "closed"}),
        "onboarding_ready": onboarding_ready,
        # Home shows which initial route the saved company state resolved to.
        **stored_route_state().model_dump(),
    }
