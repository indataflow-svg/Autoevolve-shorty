"""Typed read projections for the modern workflow pages.

Writes remain owned by sales_api and marketing_api. These views never infer a
provider outcome, a publication, or a future scheduled action from a draft.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from core import marketing_store, sales_store
from core.marketing_routing import RouteState, stored_route_state
from core.state import get_active_org, get_org

router = APIRouter(prefix="/company/ui", tags=["workflow-views"])


class ReplyItem(BaseModel):
    id: int
    lead_id: str
    company: str | None
    company_domain: str | None
    contact_name: str | None
    contact_role: str | None
    email: str | None
    lead_stage: str
    subject: str | None
    body: str | None
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


_REPLY_FROM = """FROM sales_interactions i JOIN sales_leads l ON l.id = i.lead_id
WHERE i.direction = 'inbound' AND i.channel = 'email' AND i.kind = 'reply'"""
_REPLY_SELECT = """SELECT i.id, i.lead_id, l.company, l.company_domain,
    l.full_name AS contact_name, l.job_title AS contact_role, l.email, l.stage AS lead_stage,
    i.subject, i.body, i.provider_message_id, i.created_at AS received_at,
    i.id = (SELECT newest.id FROM sales_interactions newest WHERE newest.lead_id = i.lead_id ORDER BY newest.created_at DESC LIMIT 1) AS is_latest_interaction"""


def _reply_item(row) -> dict:
    item = dict(row)
    item["is_latest_interaction"] = bool(item["is_latest_interaction"])
    item["can_draft_reply"] = item["is_latest_interaction"] and item["lead_stage"] != "suppressed" and bool(item["email"])
    return item


@router.get("/replies", response_model=RepliesPage)
def replies_view(
    page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=50),
    q: str = Query("", max_length=200), view: Literal["all", "latest", "suppressed"] = "all",
    sort: Literal["recent", "oldest", "company"] = "recent",
):
    conditions: list[str] = []
    values: list[object] = []
    if view == "latest":
        conditions.append("i.id = (SELECT newest.id FROM sales_interactions newest WHERE newest.lead_id = i.lead_id ORDER BY newest.created_at DESC LIMIT 1)")
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
            SUM(CASE WHEN l.stage = 'suppressed' THEN 1 ELSE 0 END) AS suppressed,
            SUM(CASE WHEN i.provider_message_id IS NOT NULL THEN 1 ELSE 0 END) AS threaded
            {_REPLY_FROM}""").fetchone()
    return {"items": [_reply_item(row) for row in rows], "total": total, "page": page,
            "page_size": page_size, "counts": {key: counts[key] or 0 for key in counts.keys()}}


@router.get("/replies/{reply_id}", response_model=ReplyItem)
def reply_detail(reply_id: int):
    with sales_store.connect() as connection:
        row = connection.execute(f"{_REPLY_SELECT} {_REPLY_FROM} AND i.id = ?", (reply_id,)).fetchone()
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
    note: str | None
    recorded_at: str | None
    source: str | None


class MeetingsPage(BaseModel):
    items: list[MeetingMarker]
    total: int
    page: int
    page_size: int
    counts: dict[str, int]


_MEETING_FROM = """FROM sales_leads l
WHERE json_extract(l.metadata_json, '$.meeting.status') = 'scheduled'"""
_MEETING_SELECT = """SELECT l.id, l.id AS lead_id, l.company, l.company_domain,
    l.full_name AS contact_name, l.job_title AS contact_role, l.email,
    json_extract(l.metadata_json, '$.meeting.status') AS status,
    json_extract(l.metadata_json, '$.meeting.scheduled_for') AS scheduled_for,
    json_extract(l.metadata_json, '$.meeting.note') AS note,
    json_extract(l.metadata_json, '$.meeting.updated_at') AS recorded_at,
    json_extract(l.metadata_json, '$.meeting.source') AS source"""


@router.get("/meetings", response_model=MeetingsPage)
def meetings_view(
    page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=50),
    q: str = Query("", max_length=200), view: Literal["all", "dated", "undated"] = "all",
    sort: Literal["recent", "oldest", "company"] = "recent",
):
    conditions: list[str] = []
    values: list[object] = []
    if view == "dated":
        conditions.append("json_extract(l.metadata_json, '$.meeting.scheduled_for') IS NOT NULL")
    elif view == "undated":
        conditions.append("json_extract(l.metadata_json, '$.meeting.scheduled_for') IS NULL")
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
            SUM(CASE WHEN json_extract(l.metadata_json, '$.meeting.note') IS NOT NULL THEN 1 ELSE 0 END) AS with_note
            {_MEETING_FROM}""").fetchone()
    return {"items": [dict(row) for row in rows], "total": total, "page": page,
            "page_size": page_size, "counts": {key: counts[key] or 0 for key in counts.keys()}}


@router.get("/meetings/{lead_id}", response_model=MeetingMarker)
def meeting_detail(lead_id: str):
    with sales_store.connect() as connection:
        row = connection.execute(f"{_MEETING_SELECT} {_MEETING_FROM} AND l.id = ?", (lead_id,)).fetchone()
    if not row:
        raise HTTPException(404, "recorded meeting marker not found")
    return dict(row)


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


def _outreach_item(row) -> dict:
    value = dict(row)
    return {key: value.get(key) for key in OutreachItem.model_fields}


@router.get("/outreach", response_model=OutreachPage)
def outreach_view(
    page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=50),
    q: str = Query("", max_length=200), status: str = Query("", max_length=40),
    sort: Literal["recent", "oldest", "company"] = "recent",
):
    where: list[str] = []
    values: list[object] = []
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
        counts = connection.execute("SELECT status, COUNT(*) AS count FROM sales_drafts GROUP BY status").fetchall()
    return {"items": [_outreach_item(row) for row in rows], "total": total, "page": page,
            "page_size": page_size, "by_status": {row["status"]: row["count"] for row in counts}}


@router.get("/outreach/{draft_id}", response_model=OutreachItem)
def outreach_detail(draft_id: str):
    with sales_store.connect() as connection:
        row = connection.execute(
            "SELECT d.id, d.lead_id, l.company, l.company_domain, l.full_name AS contact_name, "
            "l.job_title AS contact_role, l.email, d.channel, d.kind, d.status, d.subject, d.body, "
            "d.in_reply_to, d.created_at, d.updated_at, d.approved_at, d.sent_at "
            "FROM sales_drafts d JOIN sales_leads l ON l.id = d.lead_id WHERE d.id = ?", (draft_id,),
        ).fetchone()
    if not row:
        raise HTTPException(404, "draft not found")
    return _outreach_item(row)


class CampaignItem(BaseModel):
    id: str
    org_id: int
    org_name: str | None
    topic: str
    objective: str
    buyer: str
    status: str
    current_stage: str
    g3_status: str
    social_platforms: list[str]
    video_platform: str
    script_available: bool
    selected_variant_id: str | None
    created_at: str
    updated_at: str
    error: str | None


class CampaignVariant(BaseModel):
    id: str
    platform: str
    status: str


class CampaignDetail(CampaignItem):
    script_text: str | None
    variants: list[CampaignVariant]


class CampaignsPage(BaseModel):
    items: list[CampaignItem]
    total: int
    page: int
    page_size: int
    by_status: dict[str, int]
    active_org_id: int | None


def _campaign_item(campaign: dict) -> dict:
    org = get_org(campaign["org_id"])
    return {
        "id": campaign["id"], "org_id": campaign["org_id"], "org_name": org["name"] if org else None,
        "topic": campaign["topic"], "objective": campaign["objective"], "buyer": campaign["buyer"],
        "status": campaign["status"], "current_stage": campaign["current_stage"],
        "g3_status": campaign["g3_status"], "social_platforms": campaign["social_platforms"],
        "video_platform": campaign["video_platform"], "script_available": bool(campaign.get("g1_output_path")),
        "selected_variant_id": campaign.get("selected_variant_id"), "created_at": campaign["created_at"],
        "updated_at": campaign["updated_at"], "error": campaign.get("error"),
    }


@router.get("/campaigns", response_model=CampaignsPage)
def campaigns_view(
    page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=50),
    q: str = Query("", max_length=200), status: str = Query("", max_length=40),
    org_id: int | None = Query(None, ge=1),
    sort: Literal["recent", "oldest", "name"] = "recent",
):
    where: list[str] = []
    values: list[object] = []
    if status:
        where.append("status = ?")
        values.append(status)
    if org_id:
        where.append("org_id = ?")
        values.append(org_id)
    if q.strip():
        pattern = f"%{q.strip().replace('%', '').replace('_', '')}%"
        where.append("(topic LIKE ? OR objective LIKE ?)")
        values.extend([pattern, pattern])
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    ordering = {"recent": "updated_at DESC, id DESC", "oldest": "updated_at ASC, id ASC",
                "name": "topic COLLATE NOCASE ASC, id ASC"}[sort]
    with marketing_store.connect() as connection:
        total = connection.execute(f"SELECT COUNT(*) FROM marketing_campaigns {clause}", values).fetchone()[0]
        ids = [row["id"] for row in connection.execute(
            f"SELECT id FROM marketing_campaigns {clause} ORDER BY {ordering} LIMIT ? OFFSET ?",
            [*values, page_size, (page - 1) * page_size],
        ).fetchall()]
        counts = connection.execute("SELECT status, COUNT(*) AS count FROM marketing_campaigns GROUP BY status").fetchall()
    items = [_campaign_item(value) for item_id in ids if (value := marketing_store.get_campaign(item_id))]
    active = get_active_org()
    return {"items": items, "total": total, "page": page, "page_size": page_size,
            "by_status": {row["status"]: row["count"] for row in counts},
            "active_org_id": active["id"] if active else None}


@router.get("/campaigns/{campaign_id}", response_model=CampaignDetail)
def campaign_detail(campaign_id: str):
    from app.marketing_api import _artifact_summary

    campaign = marketing_store.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(404, "campaign not found")
    artifacts = _artifact_summary(campaign) if campaign.get("g1_output_path") else {}
    script = artifacts.get("script") if isinstance(artifacts, dict) else None
    script_text = script.get("transcript") if isinstance(script, dict) else None
    return {
        **_campaign_item(campaign), "script_text": script_text,
        "variants": [
            {"id": str(value["id"]), "platform": str(value["platform"]),
             "status": str(value["status"])}
            for value in campaign.get("variants", [])
        ],
    }


class ContentItem(BaseModel):
    id: str
    kind: Literal["manual_post", "asset_pack"]
    title: str
    org_name: str | None
    format: str
    stage: str
    buffer_status: str | None
    caption: str | None
    platform: str | None
    asset_count: int
    asset_urls: list[str]
    updated_at: str | None
    buffer_post_ids: list[str]
    buffer_accounts: list[str]
    buffer_scheduled_at: str | None


class ContentView(BaseModel):
    items: list[ContentItem]
    manual_posts_loaded: int
    asset_packs_loaded: int
    manual_posts_truncated: bool
    asset_packs_truncated: bool


@router.get("/content", response_model=ContentView)
def content_view():
    from app.marketing_api import _manual_post_buffer_status, _manual_post_status, _public_asset_pack, list_asset_packs

    manual = marketing_store.list_manual_posts(limit=200)
    with marketing_store.connect() as connection:
        manual_total = connection.execute("SELECT COUNT(*) FROM marketing_manual_posts").fetchone()[0]
    items = []
    for post in manual:
        metadata = post.get("metadata") or {}
        org = get_org(post["org_id"])
        items.append({
            "id": post["id"], "kind": "manual_post", "title": post.get("title") or metadata.get("generated_title") or post["post_id"],
            "org_name": org["name"] if org else None, "format": metadata.get("post_type") or "manual post",
            "stage": _manual_post_status(post), "buffer_status": _manual_post_buffer_status(post),
            "caption": metadata.get("generated_caption") or post.get("creative"), "platform": post["platform"],
            "asset_count": len(post.get("assets") or []),
            "asset_urls": [f"/company/marketing/manual-posts/{post['id']}/assets/{index}" for index in range(len(post.get("assets") or []))],
            "updated_at": post["updated_at"],
            "buffer_post_ids": [str(value) for value in metadata.get("buffer_post_ids") or [] if value],
            "buffer_accounts": [str(value) for value in metadata.get("buffer_accounts") or [] if value],
            "buffer_scheduled_at": metadata.get("buffer_scheduled_at"),
        })
    active = get_active_org()
    packs = list_asset_packs(project_slug=active["slug"], limit=100) if active else []
    for pack in packs:
        public_pack = _public_asset_pack(pack)
        items.append({
            "id": str(pack["id"]), "kind": "asset_pack", "title": pack.get("title") or pack["id"],
            "org_name": active["name"], "format": "asset pack", "stage": pack.get("status") or "ready",
            "buffer_status": None, "caption": pack.get("source_excerpt"), "platform": pack.get("video_platform"),
            "asset_count": len(public_pack["assets"]),
            "asset_urls": [asset["asset_url"] for asset in public_pack["assets"]], "updated_at": pack.get("updated_at"),
            "buffer_post_ids": [], "buffer_accounts": [], "buffer_scheduled_at": None,
        })
    items.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    pack_root = None
    if active:
        from app.marketing_api import PROJECTS_ROOT
        pack_root = PROJECTS_ROOT / active["slug"] / "marketing" / "asset_packs"
    pack_total = sum(item.is_dir() for item in pack_root.iterdir()) if pack_root and pack_root.is_dir() else 0
    return {"items": items, "manual_posts_loaded": len(manual), "asset_packs_loaded": len(packs),
            "manual_posts_truncated": manual_total > len(manual), "asset_packs_truncated": pack_total > len(packs)}


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
    campaigns_total: int
    manual_posts_total: int
    active_org_name: str | None
    recent_contacts: list[RecentContact]
    recent_campaigns: list[CampaignItem]
    drafts_waiting_approval: int
    campaigns_awaiting_review: int
    latest_replies: int
    open_provider_incidents: int
    onboarding_status: str


@router.get("/home", response_model=HomeView)
def home_view():
    from core.ops_store import list_incidents
    from core.state import get_onboarding_program

    active = get_active_org()
    with sales_store.connect() as connection:
        contacts_total = connection.execute("SELECT COUNT(*) FROM sales_leads").fetchone()[0]
        draft_rows = connection.execute("SELECT status, COUNT(*) AS count FROM sales_drafts GROUP BY status").fetchall()
        latest_replies = connection.execute("""SELECT COUNT(*) FROM sales_interactions i
            WHERE i.direction = 'inbound' AND i.channel = 'email' AND i.kind = 'reply'
            AND i.id = (SELECT newer.id FROM sales_interactions newer WHERE newer.lead_id = i.lead_id ORDER BY newer.created_at DESC, newer.id DESC LIMIT 1)""").fetchone()[0]
        contact_rows = connection.execute(
            "SELECT id, full_name, company, stage, updated_at FROM sales_leads ORDER BY updated_at DESC LIMIT 5"
        ).fetchall()
    draft_counts = {row["status"]: row["count"] for row in draft_rows}
    with marketing_store.connect() as connection:
        campaigns_total = connection.execute("SELECT COUNT(*) FROM marketing_campaigns").fetchone()[0]
        manual_posts_total = connection.execute("SELECT COUNT(*) FROM marketing_manual_posts").fetchone()[0]
        campaigns_awaiting_review = connection.execute("SELECT COUNT(*) FROM marketing_campaigns WHERE status = 'needs_campaign_review'").fetchone()[0]
    program = get_onboarding_program()
    incidents = list_incidents(limit=100)
    recent_campaigns = [_campaign_item(value) for value in marketing_store.list_campaigns(limit=5)]
    return {
        "contacts_total": contacts_total, "outreach_drafts_total": sum(draft_counts.values()),
        "outreach_approved_total": draft_counts.get("approved", 0),
        "outreach_unknown_total": draft_counts.get("send_unknown", 0),
        "campaigns_total": campaigns_total, "manual_posts_total": manual_posts_total,
        "active_org_name": active["name"] if active else None,
        "recent_contacts": [dict(row) for row in contact_rows], "recent_campaigns": recent_campaigns,
        "drafts_waiting_approval": draft_counts.get("draft", 0),
        "campaigns_awaiting_review": campaigns_awaiting_review,
        "latest_replies": latest_replies,
        "open_provider_incidents": sum(1 for item in incidents if item and item["status"] not in {"resolved", "closed"}),
        "onboarding_status": "not_started" if not program else "activated" if program.get("activated_at") else program.get("status", "setup_started"),
        # Home shows which initial route the saved company state resolved to.
        **stored_route_state().model_dump(),
    }
