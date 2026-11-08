from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import shutil
import urllib.request
from pathlib import Path
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, BackgroundTasks, Body, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field, field_validator
from fastapi.responses import FileResponse
from PIL import Image

from core.marketing_store import (
    create_manual_post,
    get_manual_post as _get_manual_post,
    list_manual_posts,
    update_manual_post,
)


def get_manual_post(post_id: str):
    """Read a post inside the request's org boundary.

    Basic-auth/operator requests have no scoped org and keep the legacy
    behavior. A website session can only resolve its own organization's posts.
    """
    post = _get_manual_post(post_id)
    if post and _scoped_org_id() and int(post.get("org_id") or 0) != _scoped_org_id():
        return None
    return post
from core.marketing_config import MarketingConfig
from core.branding import company_forms_url
from core.state import now_iso
from dotenv import dotenv_values
from app.sales_api import verify_founder_action
from services.caption_variants import build_short_caption_variants, enrich_platform_copy, _buyer_label
from services.g3_cli import last_json as _last_json, run as _run
from services.publishers import (
    PublisherError,
    capabilities_dict,
    catalog as publisher_catalog,
    get_publisher,
)
from core.sales_store import connect as sales_connect


router = APIRouter(prefix="/company/marketing", tags=["marketing"])
ROOT = Path(__file__).parent.parent.resolve()


class ManualPostSessionRequest(BaseModel):
    platform: str = Field(min_length=1, max_length=40)
    post_type: str = Field(default="carousel", min_length=3, max_length=20)
    destination_url: str | None = Field(default=None, max_length=500)
    link_label: str | None = Field(default=None, max_length=80)
    org_id: int | None = Field(default=None, ge=1)
    buffer_account: str | None = Field(default=None, max_length=40)
    publisher: str | None = Field(default=None, max_length=40)

    @field_validator("platform", "post_type", mode="before")
    @classmethod
    def _normalize_choice(cls, value: object) -> str:
        return str(value or "").strip().lower()

    @field_validator("destination_url", "link_label", mode="before")
    @classmethod
    def _clean_optional(cls, value: object) -> object:
        text = str(value or "").strip()
        return text or None


class ManualPostPreviewRequest(BaseModel):
    platform: str = Field(min_length=1, max_length=40)
    post_type: str = Field(default="carousel", min_length=3, max_length=20)
    destination_url: str | None = Field(default=None, max_length=500)
    link_label: str | None = Field(default=None, max_length=80)
    filenames: list[str] = Field(default_factory=list)

    @field_validator("platform", "post_type", mode="before")
    @classmethod
    def _normalize_choice(cls, value: object) -> str:
        return str(value or "").strip().lower()

    @field_validator("destination_url", "link_label", mode="before")
    @classmethod
    def _clean_optional(cls, value: object) -> object:
        text = str(value or "").strip()
        return text or None


class BufferScheduleRequest(BaseModel):
    mode: str = Field(default="queue", min_length=3, max_length=20)
    due_at: str | None = Field(default=None, max_length=100)

    @field_validator("mode", mode="before")
    @classmethod
    def _normalize_mode(cls, value: object) -> object:
        text = str(value or "queue").strip().lower()
        if text not in {"queue", "next", "timed"}:
            raise ValueError("mode must be queue, next, or timed")
        return text

    @field_validator("due_at", mode="before")
    @classmethod
    def _clean_due_at(cls, value: object) -> object:
        text = str(value or "").strip()
        return text or None


class PublishRequest(BaseModel):
    action: Literal["draft", "schedule"] = "schedule"
    mode: str = Field(default="queue", min_length=3, max_length=20)
    due_at: str | None = Field(default=None, max_length=100)
    account: str | None = Field(default=None, max_length=40)

    @field_validator("mode", mode="before")
    @classmethod
    def _normalize_mode(cls, value: object) -> object:
        text = str(value or "queue").strip().lower()
        if text not in {"queue", "next", "timed"}:
            raise ValueError("mode must be queue, next, or timed")
        return text

    @field_validator("due_at", "account", mode="before")
    @classmethod
    def _clean_optional(cls, value: object) -> object:
        text = str(value or "").strip()
        return text or None


class BufferAccountInfo(BaseModel):
    name: str
    organization_id: str | None
    instagram_channel_id: bool
    x_channel_id: bool
    linkedin_channel_id: bool = False


class BufferAccountsView(BaseModel):
    accounts: list[BufferAccountInfo]
    error: str | None = None


class BufferMetric(BaseModel):
    type: str
    name: str
    value: float
    unit: str


class BufferInsightsView(BaseModel):
    post_id: str
    buffer_account: str
    status: str
    due_at: str | None
    external_link: str | None
    metrics: list[BufferMetric] | None
    metrics_updated_at: str | None
    experimental: bool = True


class MarketingOrgActionRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    name: str
    slug: str
    domain: str | None = None
    status: str | None = None
    capabilities: dict[str, bool] = Field(default_factory=dict)


class MarketingOrgCreateResult(BaseModel):
    ok: bool
    org: MarketingOrgActionRecord


class MarketingOrgActiveResult(BaseModel):
    ok: bool
    org: MarketingOrgActionRecord


class OrgCapabilitiesResult(BaseModel):
    org_id: int
    capabilities: dict[str, bool]


class ManualPostActionRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    workflow_status: str
    buffer_status: str


class ManualPostCreateResult(BaseModel):
    ok: bool
    post: ManualPostActionRecord
    message: str


class ManualPostPreviewView(BaseModel):
    """What a manual post will look like before anything is persisted."""

    platform: str
    post_type: str
    destination_url: str
    default_destination_url: str
    link_label: str
    tracked_url: str
    caption: str
    cta: str
    title: str


class BufferScheduleResult(BaseModel):
    ok: bool
    post: ManualPostActionRecord
    result: dict[str, Any]
    message: str


class BufferSendConfirmation(BaseModel):
    checked_at: str
    overall: str
    posts: dict[str, Any]


class BufferConfirmResult(BaseModel):
    ok: bool
    post: ManualPostActionRecord
    confirmation: BufferSendConfirmation
    message: str


BUFFER_ACCOUNT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,30}$")
MAX_BUFFER_ACCOUNTS = 5


def _clean_buffer_accounts(value: object) -> list[str]:
    raw = str(value or "default").strip().lower() or "default"
    names: list[str] = []
    for part in raw.split(","):
        name = part.strip()
        if not name:
            continue
        if not BUFFER_ACCOUNT_RE.fullmatch(name):
            raise HTTPException(422, "invalid buffer account name: use lowercase letters, digits, - or _")
        if name not in names:
            names.append(name)
    if not names:
        names = ["default"]
    if len(names) > MAX_BUFFER_ACCOUNTS:
        raise HTTPException(422, f"at most {MAX_BUFFER_ACCOUNTS} buffer accounts per action")
    return names


def _g3_account_args(account: str) -> list[str]:
    return ["--account", account] if account != "default" else []


PROJECTS_ROOT = (ROOT / "projects").resolve()
@router.get("/doctor")
def doctor():
    config = MarketingConfig.load()
    checks = config.diagnostics()
    return {"ok": all(item["ok"] for item in checks.values()), "checks": checks, "draft_only": True}


def _forms_base_url() -> str:
    return (
        str(os.getenv("MARKETING_FORMS_BASE_URL") or "").strip()
        or company_forms_url()
    )


def _forms_host_label() -> str:
    value = _forms_base_url()
    parts = urlsplit(value)
    return parts.netloc or parts.path or "your form"


def _normalize_destination_url(value: str | None) -> str:
    candidate = (value or "").strip() or _forms_base_url()
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    parts = urlsplit(candidate)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise HTTPException(422, "destination URL must be a valid http(s) URL")
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", parts.query, parts.fragment))


def _generated_post_id(platform: str, post_type: str = "carousel") -> str:
    return f"{platform}_{post_type}_{now_iso().replace('-', '').replace(':', '').replace('T', '_')[:15]}"


def _generated_campaign_id(platform: str, post_type: str = "carousel") -> str:
    return f"mkt_{platform}_{post_type}_{now_iso()[:7].replace('-', '')}"


def _generated_source_detail(platform: str, post_type: str = "carousel") -> str:
    return f"{platform}_{post_type}"


def _generated_utm_campaign(platform: str, post_type: str = "carousel") -> str:
    return f"{platform}_{post_type}_{now_iso()[:7].replace('-', '')}"


def _manual_post_asset_root(project_slug: str, post_id: str) -> Path:
    return PROJECTS_ROOT / project_slug / "marketing" / "manual_posts" / post_id


def _manual_post_status(post: dict) -> str:
    metadata = post.get("metadata") or {}
    return str(metadata.get("workflow_status") or "saved").strip() or "saved"


def _manual_post_buffer_status(post: dict) -> str:
    metadata = post.get("metadata") or {}
    return str(metadata.get("buffer_status") or "not_started").strip() or "not_started"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


R2_MEDIA_KEYS = (
    "R2_ACCOUNT_ID",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_BUCKET",
    "R2_PUBLIC_BASE_URL",
)


def _missing_r2_media_keys(g3_env_file: Path | None) -> list[str]:
    """Merged view of the environment G3 will actually see (file wins)."""
    merged = dict(os.environ)
    if g3_env_file and g3_env_file.is_file():
        for key, value in dotenv_values(g3_env_file).items():
            if value is not None:
                merged[key] = value
    return [key for key in R2_MEDIA_KEYS if not merged.get(key, "").strip()]


def _require_r2_media_hosting(post: dict, config: MarketingConfig) -> None:
    """Fail fast when a post with media cannot be hosted for Buffer.

    G3 uploads every media file to R2 and hands Buffer the public URLs, so
    without these keys the subprocess dies with an opaque RuntimeError.
    Posts without local media (text-only X) skip R2 entirely.
    """
    if not (post.get("assets") or []):
        return
    missing = _missing_r2_media_keys(config.g3_env_file)
    if missing:
        raise HTTPException(
            409,
            f"media hosting (R2) is not configured ({', '.join(missing)} missing): "
            "add the R2 keys in Integrations → Setup → Media hosting (R2). "
            "Buffer needs public media URLs and G3 hosts post media on R2.",
        )


def _manual_post_handoff(post: dict) -> tuple[Path, Path]:
    metadata = post.get("metadata") or {}
    platform = str(post.get("platform") or "instagram").strip().lower()
    if platform not in {"instagram", "x", "linkedin"}:
        raise HTTPException(409, "manual Buffer drafts currently support Instagram, X, and LinkedIn")
    asset_dir = Path(str(post.get("asset_dir") or "")).resolve()
    try:
        asset_dir.relative_to(PROJECTS_ROOT)
    except ValueError as exc:
        raise HTTPException(403, "asset path is outside the company workspace") from exc
    assets = post.get("assets") or []
    if not assets:
        raise HTTPException(422, "upload and finalize the post before pushing to Buffer")
    media = []
    asset_hashes = []
    for asset in assets:
        filename = str(asset.get("filename") or "").strip()
        if not filename:
            continue
        file_path = (asset_dir / filename).resolve()
        if not file_path.is_file():
            raise HTTPException(409, f"asset file is missing: {filename}")
        try:
            file_path.relative_to(asset_dir)
        except ValueError as exc:
            raise HTTPException(403, "asset file is outside the manual post asset root") from exc
        digest = _sha256(file_path)
        asset_hashes.append(digest)
        media.append({"path": filename, "sha256": digest})
    if not media:
        raise HTTPException(422, "no usable assets found for Buffer handoff")
    if platform == "x" and len(media) > 4:
        raise HTTPException(422, "X drafts are limited to 4 media assets")
    source_package_sha256 = hashlib.sha256((str(post.get("post_id") or "") + "|" + str(metadata.get("generated_caption") or "") + "|" + "|".join(asset_hashes)).encode("utf-8")).hexdigest()
    draft_entry = {"platform": platform}
    if platform == "x":
        draft_entry["thread"] = [{"content": str(metadata.get("generated_caption") or post.get("caption") or ""), "media": media}]
    else:
        draft_entry["content"] = str(metadata.get("generated_caption") or post.get("caption") or "")
        draft_entry["media"] = media
    handoff = {
        "schema": "company-core.g3-handoff.v1",
        "campaign_id": str(post.get("campaign_id") or metadata.get("generated_campaign_id") or post.get("post_id")),
        "source_package_sha256": source_package_sha256,
        "publish_allowed": False,
        "drafts": [draft_entry],
    }
    handoff_path = asset_dir / "g3_manual_handoff.json"
    handoff_path.write_text(json.dumps(handoff, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return handoff_path, asset_dir


def _asset_tokens(assets: list[dict[str, Any]]) -> list[str]:
    stopwords = {"slide", "slides", "carousel", "page", "image", "img", "post", "cover", "final", "draft", "copy", "v1", "v2", "v3", "png", "jpg", "jpeg", "webp", "and", "the", "with", "from"}
    words: list[str] = []
    for asset in assets:
        stem = Path(str(asset.get("filename") or "")).stem
        for token in re.split(r"[^a-zA-Z0-9]+", stem.lower()):
            if len(token) < 3 or token in stopwords or token.isdigit():
                continue
            words.append(token)
    seen: list[str] = []
    for word in words:
        if word not in seen:
            seen.append(word)
    return seen


def _asset_seed(assets: list[dict[str, Any]]) -> str:
    words = _asset_tokens(assets)
    if not words:
        return ""
    return " ".join(word.capitalize() for word in words[:3])


def _caption_cta(platform: str, label: str, tracked_url: str | None = None) -> str:
    host = _forms_host_label()
    if platform == "instagram":
        return f"🔗 Link in bio · {label}"
    return f"🔗 Get the {label}: {tracked_url or host}"


def _caption_context(platform: str, tokens: list[str]) -> tuple[str, str, str]:
    joined = set(tokens)
    if {"trade", "data"}.issubset(joined):
        return (
            "⚠️ Bad trade data breaks good ops.",
            "Clean records, traceable handoffs, and AI-backed checks reduce avoidable delay.",
            _caption_cta(platform, "ops audit"),
        )
    if "customs" in joined:
        return (
            "🛃 Customs delays start before the border.",
            "Late files, weak validation, and missing ownership create costly hold-ups.",
            _caption_cta(platform, "customs workflow audit"),
        )
    if "automation" in joined and "control" in joined:
        return (
            "🤖 Automation without control creates rework.",
            "The gain comes from approvals, audit trails, and clean operating records.",
            _caption_cta(platform, "control checklist"),
        )
    if "record" in joined:
        return (
            "🧾 Build the record before the AI layer.",
            "When the workflow is structured first, follow-up, review, and reporting move faster.",
            _caption_cta(platform, "record-first audit"),
        )
    if "operator" in joined or "operators" in joined:
        return (
            "👷 AI should support the operator, not replace them.",
            "Better visibility and cleaner actions help teams move with less manual chasing.",
            _caption_cta(platform, "operator workflow audit"),
        )
    if "workflow" in joined or "handoff" in joined:
        return (
            "⚙️ Workflow gaps compound across every handoff.",
            "One missing update can slow documents, approvals, delivery timing, and follow-through.",
            _caption_cta(platform, "workflow audit"),
        )
    if "visibility" in joined or "control" in joined:
        return (
            "📊 Visibility is only useful when control follows.",
            "Teams need clear next actions, not just more dashboards and alerts.",
            _caption_cta(platform, "ops visibility audit"),
        )
    if "demurrage" in joined or "delay" in joined or "delays" in joined:
        return (
            "⏱️ Delay costs stack long before finance sees them.",
            "The fix is earlier coordination across records, owners, and customer communication.",
            _caption_cta(platform, "delay-reduction audit"),
        )
    return (
        "⚙️ Tighten the workflow before scale adds noise.",
        "Standardized records, faster approvals, and clearer ownership keep ops moving.",
        _caption_cta(platform, "ops audit"),
    )


def _generated_caption(
    platform: str,
    assets: list[dict[str, Any]],
    *,
    link_label: str = "ops audit",
    tracked_url: str | None = None,
) -> str:
    line1, line2, _ = _caption_context(platform, _asset_tokens(assets))
    return f"{line1}\n{line2}\n{_caption_cta(platform, link_label, tracked_url)}"


def _tracked_post_url(destination_url: str, *, platform: str, post_id: str, campaign_id: str, utm_campaign: str, source_detail: str, post_type: str = "carousel") -> str:
    parts = urlsplit(destination_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update({
        "utm_source": platform,
        "utm_medium": post_type,
        "utm_campaign": utm_campaign,
        "campaign_id": campaign_id,
        "post_id": post_id,
        "source_detail": source_detail,
    })
    encoded = urlencode({key: value for key, value in query.items() if value != ""})
    return urlunsplit((parts.scheme, parts.netloc, parts.path, encoded, parts.fragment))


def _lead_attribution(post: dict) -> dict[str, Any]:
    post_id = post.get("post_id")
    with sales_connect() as connection:
        rows = connection.execute(
            "SELECT stage, COUNT(*) AS count FROM sales_leads WHERE post_id = ? GROUP BY stage",
            (post_id,),
        ).fetchall()
    by_stage = {row["stage"]: int(row["count"]) for row in rows}
    return {
        "leads": sum(by_stage.values()),
        "qualified": by_stage.get("qualified", 0),
        "draft_ready": by_stage.get("draft_ready", 0),
        "approved": by_stage.get("approved", 0),
        "contacted": by_stage.get("contacted", 0),
        "replied": by_stage.get("replied", 0),
        "won": by_stage.get("won", 0),
        "suppressed": by_stage.get("suppressed", 0),
        "by_stage": by_stage,
    }


def _public_manual_post(post: dict) -> dict:
    metadata = post.get("metadata") or {}
    value = {
        key: post.get(key)
        for key in (
            "id", "org_id", "platform", "post_id", "tracked_url", "source_detail", "asset_dir", "created_at", "updated_at",
        )
    }
    value["campaign_id"] = post.get("campaign_id") or metadata.get("generated_campaign_id")
    value["title"] = post.get("title") or metadata.get("generated_title") or value["post_id"]
    value["creative"] = post.get("creative") or metadata.get("generated_creative")
    value["hook"] = post.get("hook") or metadata.get("generated_hook")
    value["offer"] = post.get("offer") or metadata.get("generated_offer")
    value["cta"] = post.get("cta") or metadata.get("generated_cta")
    value["destination_url"] = post.get("destination_url") or metadata.get("destination_url") or _forms_base_url()
    value["post_type"] = metadata.get("post_type") or "carousel"
    value["link_label"] = metadata.get("link_label") or "ops audit"
    value["caption"] = metadata.get("generated_caption") or _generated_caption(
        value["platform"],
        post.get("assets") or [],
        link_label=value["link_label"],
        tracked_url=value.get("tracked_url"),
    )
    value["utm_campaign"] = metadata.get("utm_campaign")
    value["preferred_buffer_account"] = metadata.get("preferred_buffer_account")
    value["workflow_status"] = _manual_post_status(post)
    value["buffer_status"] = _manual_post_buffer_status(post)
    value["publisher"] = metadata.get("publisher") or "buffer"
    value["publisher_status"] = metadata.get("publisher_status") or value["buffer_status"]
    value["publisher_post_ids"] = metadata.get("publisher_post_ids") or metadata.get("buffer_post_ids") or []
    value["publisher_account"] = metadata.get("publisher_account") or metadata.get("buffer_account")
    value["publisher_scheduled_at"] = metadata.get("publisher_scheduled_at") or metadata.get("buffer_scheduled_at")
    value["publisher_send_confirmation"] = metadata.get("publisher_send_confirmation") or metadata.get("buffer_send_confirmation")
    value["buffer_ready"] = value["workflow_status"] in {"ready", "buffer_draft", "scheduled", "published"}
    value["asset_count"] = len(post.get("assets") or [])
    value["assets"] = []
    for index, asset in enumerate(post.get("assets") or []):
        item = dict(asset)
        item["asset_url"] = f"/company/marketing/manual-posts/{post['id']}/assets/{index}"
        value["assets"].append(item)
    value["metadata"] = metadata
    value["attribution"] = _lead_attribution(post)
    org_id = post.get("org_id")
    if org_id:
        from core.state import get_org
        org = get_org(org_id)
        value["org_name"] = org["name"] if org else None
        value["org_slug"] = org["slug"] if org else None
    else:
        value["org_name"] = None
        value["org_slug"] = None
    return value


@router.post("/manual-posts/preview", response_model=ManualPostPreviewView)
def preview_manual_post(payload: ManualPostPreviewRequest):
    """Preview the caption and tracking link a manual post will receive.

    Read-only: nothing is persisted and no provider is called. It reuses the
    exact helpers the create path uses, so the operator sees the real caption
    instead of a client-side approximation that could drift.
    """
    clean_platform = payload.platform.strip().lower()
    if clean_platform not in {"instagram", "x", "linkedin"}:
        raise HTTPException(422, "unsupported platform")
    post_type = payload.post_type.strip().lower()
    if post_type not in {"carousel", "video"}:
        raise HTTPException(422, "post_type must be carousel or video")
    destination_url = _normalize_destination_url(payload.destination_url)
    link_label = (payload.link_label or "").strip() or "ops audit"
    filenames = [Path(str(name)).name for name in payload.filenames if str(name).strip()]
    assets = [{"filename": name} for name in filenames[:20]]
    tracked_url = _tracked_post_url(
        destination_url,
        platform=clean_platform,
        post_id=_generated_post_id(clean_platform, post_type),
        campaign_id=_generated_campaign_id(clean_platform, post_type),
        utm_campaign=_generated_utm_campaign(clean_platform, post_type),
        source_detail=_generated_source_detail(clean_platform, post_type),
        post_type=post_type,
    )
    return ManualPostPreviewView(
        platform=clean_platform,
        post_type=post_type,
        destination_url=destination_url,
        default_destination_url=_forms_base_url(),
        link_label=link_label,
        tracked_url=tracked_url,
        caption=_generated_caption(clean_platform, assets, link_label=link_label, tracked_url=tracked_url),
        cta=_caption_cta(clean_platform, link_label, tracked_url),
        title=_asset_seed(assets) or f"{clean_platform.title()} {post_type}",
    )


@router.post("/manual-posts/session")
def create_manual_post_session(payload: ManualPostSessionRequest):
    from core.state import get_active_org, get_org

    from core.auth_context import current_org_id

    scoped_org = current_org_id.get()
    if scoped_org and payload.org_id is not None and int(payload.org_id) != int(scoped_org):
        raise HTTPException(404, "org not found")
    if payload.org_id is not None and not scoped_org:
        org = get_org(payload.org_id)
        if not org:
            raise HTTPException(404, "org not found")
    else:
        org = get_org(int(scoped_org)) if scoped_org else get_active_org()
        if not org:
            raise HTTPException(409, "set an active org before saving a manual post")
    clean_platform = payload.platform.strip().lower()
    if clean_platform not in {"instagram", "x", "linkedin"}:
        raise HTTPException(422, "unsupported platform")
    post_type = payload.post_type.strip().lower()
    if post_type not in {"carousel", "video"}:
        raise HTTPException(422, "post_type must be carousel or video")
    is_free = (org.get("plan") or "paid") == "free"
    publisher_name = (payload.publisher or ("webhook" if is_free else "buffer")).strip().lower()
    if is_free and publisher_name != "webhook":
        raise HTTPException(403, "free workspaces publish through their own webhook connection")
    try:
        selected_publisher = get_publisher(publisher_name)
    except PublisherError as exc:
        raise HTTPException(422, str(exc)) from exc
    if publisher_name != "buffer" and not selected_publisher.accounts():
        raise HTTPException(409, f"{publisher_name} publisher is not configured")
    if publisher_name == "buffer":
        try:
            from services.buffer_setup import normalize_account_name
            preferred_account = normalize_account_name(payload.buffer_account or "default")
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    else:
        preferred_account = (payload.buffer_account or "").strip() or None
    clean_post_id = _generated_post_id(clean_platform, post_type)
    generated_campaign_id = _generated_campaign_id(clean_platform, post_type)
    generated_source_detail = _generated_source_detail(clean_platform, post_type)
    generated_utm_campaign = _generated_utm_campaign(clean_platform, post_type)
    destination_url = _normalize_destination_url(payload.destination_url)
    link_label = (payload.link_label or "ops audit").strip()
    tracked_url = _tracked_post_url(
        destination_url,
        platform=clean_platform,
        post_id=clean_post_id,
        campaign_id=generated_campaign_id,
        utm_campaign=generated_utm_campaign,
        source_detail=generated_source_detail,
        post_type=post_type,
    )
    asset_root = _manual_post_asset_root(org["slug"], clean_post_id)
    asset_root.mkdir(parents=True, exist_ok=True)
    try:
        post = create_manual_post(
            org_id=org["id"],
            campaign_id=None,
            platform=clean_platform,
            post_id=clean_post_id,
            title=f"{clean_platform.title()} {post_type}",
            creative=None,
            hook=None,
            offer=None,
            cta=None,
            destination_url=destination_url,
            tracked_url=tracked_url,
            source_detail=generated_source_detail,
            asset_dir=str(asset_root),
            assets=[],
            metadata={
                "generated_campaign_id": generated_campaign_id,
                "utm_campaign": generated_utm_campaign,
                "generated_offer": "forms access",
                "generated_cta": _caption_cta(clean_platform, link_label, tracked_url),
                "destination_url": destination_url,
                "post_type": post_type,
                "link_label": link_label,
                "workflow_status": "uploading",
                "publisher": publisher_name,
                "publisher_status": "not_started",
                "publisher_account": preferred_account,
                "buffer_status": "not_started",
                "preferred_buffer_account": preferred_account if publisher_name == "buffer" else None,
            },
        )
    except Exception as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"ok": True, "post": _public_manual_post(post), "message": f"{post_type.title()} record created. Upload media to continue."}


@router.post("/manual-posts/{post_record_id}/assets")
async def upload_manual_post_asset(post_record_id: str, asset: UploadFile = File(...)):
    post = get_manual_post(post_record_id)
    if not post:
        raise HTTPException(404, "manual post not found")
    metadata = dict(post.get("metadata") or {})
    post_type = str(metadata.get("post_type") or "carousel")
    filename = Path(asset.filename or ("video.mp4" if post_type == "video" else "asset.png")).name
    if not filename:
        raise HTTPException(422, "asset filename is required")
    suffix = Path(filename).suffix.lower()
    allowed = {".mp4"} if post_type == "video" else {".png"}
    if suffix not in allowed:
        expected = "one MP4 video" if post_type == "video" else "PNG carousel assets"
        raise HTTPException(422, f"this post requires {expected}")
    if post_type == "video" and post.get("assets"):
        raise HTTPException(422, "video posts accept exactly one MP4")
    asset_dir = Path(post.get("asset_dir") or "").resolve()
    try:
        asset_dir.relative_to(PROJECTS_ROOT)
    except ValueError as exc:
        raise HTTPException(403, "asset path is outside the company workspace") from exc
    asset_dir.mkdir(parents=True, exist_ok=True)
    target = asset_dir / filename
    with target.open("wb") as handle:
        shutil.copyfileobj(asset.file, handle)
    assets_meta = [dict(item) for item in (post.get("assets") or []) if str(item.get("filename") or "") != filename]
    assets_meta.append({
        "filename": filename,
        "content_type": asset.content_type,
        "size_bytes": target.stat().st_size,
    })
    metadata["workflow_status"] = "uploading"
    updated = update_manual_post(
        post_record_id,
        assets_json=json.dumps(assets_meta, ensure_ascii=False),
        metadata_json=json.dumps(metadata, ensure_ascii=False),
    )
    return {"ok": True, "post": _public_manual_post(updated), "message": f"Saved {filename}."}


@router.post("/manual-posts/{post_record_id}/finalize")
def finalize_manual_post(post_record_id: str):
    post = get_manual_post(post_record_id)
    if not post:
        raise HTTPException(404, "manual post not found")
    assets_meta = [dict(item) for item in (post.get("assets") or [])]
    if not assets_meta:
        raise HTTPException(422, "upload at least one media asset before finalizing")
    platform = str(post.get("platform") or "instagram").strip().lower() or "instagram"
    metadata = dict(post.get("metadata") or {})
    post_type = str(metadata.get("post_type") or "carousel")
    if post_type == "video" and len(assets_meta) != 1:
        raise HTTPException(422, "video posts require exactly one MP4")
    generated_title = _asset_seed(assets_meta) or post.get("title") or f"{platform.title()} {post_type}"
    generated_caption = _generated_caption(
        platform,
        assets_meta,
        link_label=str(metadata.get("link_label") or "ops audit"),
        tracked_url=str(post.get("tracked_url") or ""),
    )
    metadata.update({
        "generated_caption": generated_caption,
        "generated_title": generated_title,
        "generated_offer": metadata.get("generated_offer") or "forms access",
        "generated_cta": metadata.get("generated_cta") or _caption_cta(
            platform,
            str(metadata.get("link_label") or "ops audit"),
            str(post.get("tracked_url") or ""),
        ),
        "destination_url": metadata.get("destination_url") or _forms_base_url(),
        "workflow_status": "ready",
        "buffer_status": metadata.get("buffer_status") or "not_started",
    })
    updated = update_manual_post(
        post_record_id,
        title=generated_title,
        metadata_json=json.dumps(metadata, ensure_ascii=False),
    )
    publisher_name = str(metadata.get("publisher") or "buffer")
    return {"ok": True, "post": _public_manual_post(updated), "message": f"{post_type.title()} saved locally and marked ready for {publisher_name} handoff."}


@router.post("/manual-posts", response_model=ManualPostCreateResult)
async def create_manual_post_from_ui(
    platform: str = Form(...),
    post_type: str = Form(default="carousel"),
    destination_url: str | None = Form(default=None),
    link_label: str | None = Form(default=None),
    org_id: int | None = Form(default=None),
    buffer_account: str | None = Form(default=None),
    publisher: str | None = Form(default=None),
    assets: list[UploadFile] = File(default=[]),
):
    session = create_manual_post_session(ManualPostSessionRequest(
        platform=platform,
        post_type=post_type,
        destination_url=destination_url,
        link_label=link_label,
        org_id=org_id,
        buffer_account=buffer_account,
        publisher=publisher,
    ))
    post = session["post"]
    for upload in assets:
        await upload_manual_post_asset(post["id"], upload)
    finalized = finalize_manual_post(post["id"])
    return {"ok": True, "post": finalized["post"], "message": "Manual post saved with backend-generated tracking and caption."}


def _scoped_org_id() -> int:
    from core.auth_context import current_org_id

    return int(current_org_id.get() or 0)


def _ensure_org_scope(org_id: int) -> None:
    scoped = _scoped_org_id()
    if scoped and int(org_id) != scoped:
        raise HTTPException(404, "org not found")


def _block_free_buffer() -> None:
    from core.state import get_org

    scoped = _scoped_org_id()
    if scoped and (get_org(scoped) or {}).get("plan") == "free":
        raise HTTPException(403, "free workspaces use their own publisher webhook")


def _publisher_for_post(post: dict[str, Any]):
    from core.auth_context import current_org_id
    from core.state import get_org

    name = str((post.get("metadata") or {}).get("publisher") or "buffer").strip().lower()
    scoped = current_org_id.get()
    if scoped and int(post.get("org_id") or 0) != int(scoped):
        raise HTTPException(404, "manual post not found")
    if scoped:
        org = get_org(int(scoped))
        if org and (org.get("plan") or "paid") == "free" and name != "webhook":
            raise HTTPException(403, "free workspaces publish through their own webhook connection")
    try:
        return get_publisher(name)
    except PublisherError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


def _publisher_http_error(exc: PublisherError) -> HTTPException:
    return HTTPException(exc.status_code, str(exc))


@router.get("/publishers")
def publishers():
    return {"publishers": publisher_catalog()}


@router.get("/publisher-accounts")
def publisher_accounts(publisher: str | None = None):
    from core.auth_context import current_org_id
    from core.state import get_org

    scoped = current_org_id.get()
    if scoped:
        org = get_org(int(scoped))
        if org and (org.get("plan") or "paid") == "free" and (publisher or "buffer") == "buffer":
            raise HTTPException(403, "free workspaces do not use the shared Buffer account")
    try:
        selected = get_publisher(publisher)
        accounts = selected.accounts()
    except PublisherError as exc:
        raise _publisher_http_error(exc) from exc
    return {
        "publisher": selected.name,
        "label": selected.label,
        "capabilities": capabilities_dict(selected),
        "error": next((account.details.get("error") for account in accounts if account.details.get("error")), None),
        "accounts": [
            {
                "name": account.name,
                "label": account.label,
                "platforms": list(account.platforms),
                "details": account.details,
            }
            for account in accounts
        ],
    }


@router.post("/manual-posts/{post_record_id}/publish", dependencies=[Depends(verify_founder_action)])
def publish_manual_post(post_record_id: str, payload: PublishRequest):
    """Schedule a finalized manual post through its configured publisher."""
    post = get_manual_post(post_record_id)
    if not post:
        raise HTTPException(404, "manual post not found")
    selected = _publisher_for_post(post)
    try:
        if payload.action == "draft":
            return selected.draft(post, payload.account)
        return selected.schedule(
            post,
            account=payload.account,
            mode=payload.mode,
            due_at=payload.due_at,
        )
    except PublisherError as exc:
        raise _publisher_http_error(exc) from exc


@router.post("/manual-posts/{post_record_id}/publish/async", status_code=202, dependencies=[Depends(verify_founder_action)])
def queue_manual_post_publish(post_record_id: str, payload: PublishRequest, background_tasks: BackgroundTasks):
    """Queue a provider schedule so Cloudflare's ~125s edge timeout cannot
    turn a completed provider call into an ambiguous 524 response."""
    from core.jobs_store import create_publish_job
    from core.quotas import org_plan

    if payload.action != "schedule":
        raise HTTPException(422, "async publish currently supports schedule only")
    post = get_manual_post(post_record_id)
    if not post:
        raise HTTPException(404, "manual post not found")
    selected = _publisher_for_post(post)
    org_id = int(post.get("org_id") or 0)
    if org_plan(org_id) == "free" and selected.name != "webhook":
        raise HTTPException(403, "free workspaces publish through their own webhook connection")
    job = create_publish_job(org_id, post_record_id)
    background_tasks.add_task(
        _run_publish_job,
        job["id"],
        post_record_id,
        payload.model_dump(mode="json"),
    )
    return {"ok": True, "job": job}


def _run_publish_job(job_id: str, post_record_id: str, payload: dict[str, Any]) -> None:
    from core.jobs_store import update_publish_job
    from core.quotas import org_plan

    update_publish_job(job_id, status="running")
    try:
        post = _get_manual_post(post_record_id)
        if not post:
            raise PublisherError("manual post no longer exists", 404)
        org_id = int(post.get("org_id") or 0)
        selected = _publisher_for_post(post)
        if org_plan(org_id) == "free" and selected.name != "webhook":
            raise PublisherError("free workspaces publish through their own webhook connection", 403)
        result = selected.schedule(
            post,
            account=payload.get("account"),
            mode=str(payload.get("mode") or "queue"),
            due_at=payload.get("due_at"),
        )
        update_publish_job(job_id, status="completed", result=result)
    except Exception as exc:  # noqa: BLE001 - job status must record any provider failure
        update_publish_job(job_id, status="failed", error=str(exc)[:1000])


@router.get("/publish-jobs/{job_id}")
def get_publish_job_status(job_id: str):
    from core.jobs_store import get_publish_job
    from core.state import get_active_org

    active = get_active_org()
    if not active:
        raise HTTPException(409, "no active org")
    job = get_publish_job(job_id, int(active["id"]))
    if not job:
        raise HTTPException(404, "publish job not found")
    return job


@router.post("/manual-posts/{post_record_id}/publish/draft")
def draft_manual_post(post_record_id: str, payload: PublishRequest):
    """Create a provider draft. Buffer supports this; the webhook does not."""
    post = get_manual_post(post_record_id)
    if not post:
        raise HTTPException(404, "manual post not found")
    selected = _publisher_for_post(post)
    try:
        return selected.draft(post, payload.account)
    except PublisherError as exc:
        raise _publisher_http_error(exc) from exc


@router.post("/manual-posts/{post_record_id}/publish/confirm", dependencies=[Depends(verify_founder_action)])
def confirm_manual_post_publish(post_record_id: str):
    """Ask the configured publisher for the fate of every saved provider post."""
    post = get_manual_post(post_record_id)
    if not post:
        raise HTTPException(404, "manual post not found")
    selected = _publisher_for_post(post)
    try:
        return selected.confirm(post)
    except PublisherError as exc:
        raise _publisher_http_error(exc) from exc


@router.get("/manual-posts/{post_record_id}/publish/insights")
def manual_post_publish_insights(post_record_id: str, post_id: str | None = None):
    post = get_manual_post(post_record_id)
    if not post:
        raise HTTPException(404, "manual post not found")
    selected = _publisher_for_post(post)
    selected_id = post_id
    if not selected_id:
        metadata = post.get("metadata") or {}
        saved = metadata.get("publisher_post_ids") or metadata.get("buffer_post_ids") or []
        selected_id = str(saved[0]) if saved else ""
    if not selected_id:
        raise HTTPException(409, "this manual post has no saved provider post ID")
    try:
        return selected.insights(post, selected_id)
    except PublisherError as exc:
        raise _publisher_http_error(exc) from exc


@router.get("/buffer-accounts", response_model=BufferAccountsView)
def buffer_accounts():
    """Named Buffer accounts configured in g3.env (keys never leave the server)."""
    _block_free_buffer()
    try:
        from core.sales_store import connect as _connect
        with _connect() as connection:
            try:
                rows = connection.execute(
                    "SELECT name, organization_id, instagram_channel_id, x_channel_id FROM buffer_org_accounts ORDER BY name"
                ).fetchall()
            except Exception:
                rows = None
            if rows:
                accounts = [
                    {
                        "name": row["name"],
                        "organization_id": row["organization_id"],
                        "instagram_channel_id": bool(row["instagram_channel_id"]),
                        "x_channel_id": bool(row["x_channel_id"]),
                        "linkedin_channel_id": bool(row["linkedin_channel_id"]) if "linkedin_channel_id" in row.keys() else False,
                    }
                    for row in rows
                ]
                return {"accounts": accounts}
    except Exception:
        pass
    config = MarketingConfig.load()
    fallback = {"accounts": [{"name": "default", "organization_id": None,
                              "instagram_channel_id": False, "x_channel_id": False,
                              "linkedin_channel_id": False}]}
    if not config.g3_bin.is_file():
        return {**fallback, "error": f"G3 command not found: {config.g3_bin}"}
    try:
        log_dir = PROJECTS_ROOT / ".logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        output = _last_json(_run(
            [str(config.g3_bin), "accounts"],
            cwd=config.g3_root,
            env_file=config.g3_env_file,
            timeout=30,
            log_path=log_dir / "g3_accounts.log",
        ))
    except Exception as exc:
        return {**fallback, "error": f"{type(exc).__name__}: {exc}"}
    accounts = output.get("accounts") if isinstance(output, dict) else None
    if not isinstance(accounts, list) or not accounts:
        return {**fallback, "error": "G3 reported no Buffer accounts"}
    return {"accounts": accounts}


def _saved_buffer_post_ids(metadata: dict) -> list[str]:
    return [str(value) for value in metadata.get("buffer_post_ids") or [] if value]


def _buffer_account_for_post(metadata: dict, selected_id: str) -> str:
    """Which saved Buffer account owns a post ID. Shared by the read-only
    insights view and the send-confirmation pass so the two can never resolve
    the same post to different accounts."""
    account_names = set()
    for account, output in (metadata.get("buffer_result") or {}).items():
        if not isinstance(output, dict):
            continue
        for result in output.get("results") or []:
            if isinstance(result, dict) and str(result.get("post_id") or "") == selected_id:
                account_names.add(account)
    if not account_names:
        fallback = metadata.get("buffer_account")
        if fallback and len(metadata.get("buffer_accounts") or []) <= 1:
            account_names.add(str(fallback))
    if len(account_names) != 1:
        raise HTTPException(409, "Buffer account for this post cannot be determined")
    return next(iter(account_names))


def _classify_provider_status(raw: object) -> str:
    """Map Buffer's post status to an honest verdict. Only an explicit sent
    counts as sent; anything alarming counts as failed; the rest — including
    statuses Buffer invents tomorrow — stays pending, never assumed."""
    normalized = str(raw or "").strip().lower()
    if normalized == "sent":
        return "sent"
    if any(token in normalized for token in ("fail", "error", "cancel", "reject")):
        return "failed"
    return "pending"


@router.get("/manual-posts/{post_record_id}/buffer-insights", response_model=BufferInsightsView)
def manual_post_buffer_insights(post_record_id: str, post_id: str | None = None):
    """Read one saved Buffer post's provider state and optional personal-key metrics."""
    _block_free_buffer()
    post = get_manual_post(post_record_id)
    if not post:
        raise HTTPException(404, "manual post not found")
    metadata = post.get("metadata") or {}
    saved_ids = _saved_buffer_post_ids(metadata)
    if not saved_ids:
        raise HTTPException(409, "this manual post has no confirmed Buffer post ID")
    selected_id = post_id or saved_ids[0]
    if selected_id not in saved_ids:
        raise HTTPException(404, "Buffer post ID is not saved for this manual post")
    account = _buffer_account_for_post(metadata, selected_id)
    config = MarketingConfig.load()
    if not config.g3_bin.is_file():
        raise HTTPException(503, f"G3 command not found: {config.g3_bin}")
    try:
        log_dir = PROJECTS_ROOT / ".logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        output = _last_json(_run(
            [str(config.g3_bin), *_g3_account_args(account), "insights", selected_id],
            cwd=config.g3_root, env_file=config.g3_env_file, timeout=45,
            log_path=log_dir / "g3_insights.log",
        ))
    except Exception as exc:
        raise HTTPException(502, f"Buffer insights unavailable: {type(exc).__name__}: {exc}") from exc
    provider_post = output.get("post") if isinstance(output, dict) and output.get("ok") else None
    if not isinstance(provider_post, dict) or str(provider_post.get("id") or "") != selected_id:
        raise HTTPException(502, "Buffer did not confirm the requested post")
    return {
        "post_id": selected_id, "buffer_account": account,
        "status": str(provider_post.get("status") or "unknown"),
        "due_at": provider_post.get("dueAt"), "external_link": provider_post.get("externalLink"),
        "metrics": provider_post.get("metrics"), "metrics_updated_at": provider_post.get("metricsUpdatedAt"),
        "experimental": True,
    }


@router.post("/manual-posts/{post_record_id}/buffer-confirm", response_model=BufferConfirmResult, dependencies=[Depends(verify_founder_action)])
def confirm_manual_post_send(post_record_id: str):
    """Ask Buffer for the fate of every scheduled post ID and persist the verdict.

    Manual and explicit: nothing here schedules, drafts, or publishes. The
    local ``buffer_status`` is left untouched — this records what the provider
    says next to it, so "scheduled (our record)" and "sent (their word)" can
    never be confused. Only an explicit ``sent`` counts as sent.
    """
    from core.state import now_iso

    _block_free_buffer()
    post = get_manual_post(post_record_id)
    if not post:
        raise HTTPException(404, "manual post not found")
    metadata = dict(post.get("metadata") or {})
    saved_ids = _saved_buffer_post_ids(metadata)
    if not saved_ids:
        raise HTTPException(409, "this manual post has no scheduled Buffer post to confirm")
    config = MarketingConfig.load()
    if not config.g3_bin.is_file():
        raise HTTPException(503, f"G3 command not found: {config.g3_bin}")
    log_dir = PROJECTS_ROOT / ".logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    entries: dict[str, dict] = {}
    for selected_id in saved_ids:
        account = _buffer_account_for_post(metadata, selected_id)
        try:
            output = _last_json(_run(
                [str(config.g3_bin), *_g3_account_args(account), "insights", selected_id],
                cwd=config.g3_root, env_file=config.g3_env_file, timeout=45,
                log_path=log_dir / "g3_confirm.log",
            ))
        except Exception as exc:
            entries[selected_id] = {
                "buffer_account": account, "status": "unknown", "verdict": "unknown",
                "error": f"{type(exc).__name__}: {exc}",
            }
            continue
        provider_post = output.get("post") if isinstance(output, dict) and output.get("ok") else None
        if not isinstance(provider_post, dict) or str(provider_post.get("id") or "") != selected_id:
            entries[selected_id] = {
                "buffer_account": account, "status": "unknown", "verdict": "unknown",
                "error": "Buffer did not confirm the requested post",
            }
            continue
        raw_status = str(provider_post.get("status") or "unknown")
        entries[selected_id] = {
            "buffer_account": account, "status": raw_status,
            "verdict": _classify_provider_status(raw_status),
            "due_at": provider_post.get("dueAt"),
            "external_link": provider_post.get("externalLink"),
        }
    verdicts = {entry["verdict"] for entry in entries.values()}
    if verdicts == {"sent"}:
        overall = "sent"
    elif "failed" in verdicts:
        overall = "failed"
    elif "unknown" in verdicts:
        overall = "unknown"
    else:
        overall = "pending"
    confirmation = {"checked_at": now_iso(), "overall": overall, "posts": entries}
    metadata["buffer_send_confirmation"] = confirmation
    updated = update_manual_post(post_record_id, metadata_json=json.dumps(metadata, ensure_ascii=False))
    if overall == "sent":
        message = "Buffer confirms every scheduled post was sent."
    elif overall == "failed":
        message = "Buffer reports a failed post — see the per-post verdicts."
    elif overall == "unknown":
        message = "Buffer could not be reached for at least one post — nothing confirmed."
    else:
        message = "Buffer has not sent yet — still scheduled on the provider side."
    return {"ok": True, "post": _public_manual_post(updated), "confirmation": confirmation, "message": message}


@router.post("/manual-posts/{post_record_id}/buffer-draft")
def create_manual_post_buffer_draft(post_record_id: str, buffer_account: str | None = None):
    _block_free_buffer()
    accounts = _clean_buffer_accounts(buffer_account)
    post = get_manual_post(post_record_id)
    if not post:
        raise HTTPException(404, "manual post not found")
    if _manual_post_status(post) != "ready":
        raise HTTPException(409, "finalize the manual post before pushing it to Buffer")
    if _manual_post_buffer_status(post) in {"queued", "running"}:
        raise HTTPException(409, "Buffer draft creation is already running for this post")
    config = MarketingConfig.load()
    if not config.g3_bin.is_file():
        raise HTTPException(409, f"G3 command not found: {config.g3_bin}")
    _require_r2_media_hosting(post, config)
    metadata = dict(post.get("metadata") or {})
    metadata["buffer_status"] = "running"
    metadata["buffer_accounts"] = accounts
    metadata["buffer_account"] = accounts[0]
    update_manual_post(post_record_id, metadata_json=json.dumps(metadata, ensure_ascii=False))
    outputs: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for account in accounts:
        try:
            handoff_path, asset_root = _manual_post_handoff(post)
            outputs[account] = _last_json(_run(
                [
                    str(config.g3_bin), *_g3_account_args(account), "draft", str(handoff_path), "--asset-root", str(asset_root),
                    "--ledger", str(asset_root / "g3.sqlite3"),
                ],
                cwd=config.g3_root,
                env_file=config.g3_env_file,
                timeout=config.stage_timeout,
                log_path=asset_root / "logs" / "g3_manual.log",
            ))
        except Exception as exc:
            errors[account] = f"{type(exc).__name__}: {exc}"
    if len(errors) == len(accounts):
        failed_metadata = dict(post.get("metadata") or {})
        failed_metadata["buffer_status"] = "failed"
        failed_metadata["buffer_error"] = "; ".join(f"{name}: {error}" for name, error in errors.items())
        update_manual_post(post_record_id, metadata_json=json.dumps(failed_metadata, ensure_ascii=False))
        raise HTTPException(502, f"manual Buffer draft failed: {failed_metadata['buffer_error']}")
    completed_metadata = dict((get_manual_post(post_record_id) or post).get("metadata") or {})
    completed_metadata["buffer_status"] = "drafted"
    completed_metadata["buffer_accounts"] = accounts
    completed_metadata["buffer_account"] = accounts[0]
    completed_metadata["buffer_result"] = outputs
    if errors:
        completed_metadata["buffer_error"] = "; ".join(f"{name}: {error}" for name, error in errors.items())
    else:
        completed_metadata.pop("buffer_error", None)
    completed_metadata["workflow_status"] = "buffer_draft"
    updated = update_manual_post(post_record_id, metadata_json=json.dumps(completed_metadata, ensure_ascii=False))
    names = ", ".join(accounts)
    return {"ok": True, "post": _public_manual_post(updated), "result": outputs, "message": f"Buffer draft created for the manual post (accounts: {names})."}


@router.post("/manual-posts/{post_record_id}/buffer-schedule", response_model=BufferScheduleResult, dependencies=[Depends(verify_founder_action)])
def schedule_manual_post_buffer(post_record_id: str, payload: BufferScheduleRequest, buffer_account: str | None = None):
    _block_free_buffer()
    accounts = _clean_buffer_accounts(buffer_account)
    post = get_manual_post(post_record_id)
    if not post:
        raise HTTPException(404, "manual post not found")
    if _manual_post_status(post) != "ready" and _manual_post_status(post) not in {"buffer_draft", "scheduled"}:
        raise HTTPException(409, "finalize the manual post before scheduling it in Buffer")
    if _manual_post_buffer_status(post) in {"queued", "running"}:
        raise HTTPException(409, "Buffer scheduling is already running for this post")
    if payload.mode == "timed" and not payload.due_at:
        raise HTTPException(422, "timed scheduling requires due_at")
    from core.quotas import QuotaExceeded, enforce_quota, record_usage, retry_after_seconds

    org_id = int(post.get("org_id") or 0)
    try:
        enforce_quota(org_id, "publishes")
    except QuotaExceeded as exc:
        raise HTTPException(429, str(exc), headers={"Retry-After": str(retry_after_seconds(exc))}) from exc
    config = MarketingConfig.load()
    if not config.g3_bin.is_file():
        raise HTTPException(409, f"G3 command not found: {config.g3_bin}")
    _require_r2_media_hosting(post, config)
    metadata = dict(post.get("metadata") or {})
    metadata["buffer_status"] = "running"
    metadata["buffer_accounts"] = accounts
    metadata["buffer_account"] = accounts[0]
    update_manual_post(post_record_id, metadata_json=json.dumps(metadata, ensure_ascii=False))
    outputs: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for account in accounts:
        try:
            handoff_path, asset_root = _manual_post_handoff(post)
            command = [
                str(config.g3_bin), *_g3_account_args(account), "schedule", str(handoff_path), "--asset-root", str(asset_root),
                "--ledger", str(asset_root / "g3.sqlite3"),
                "--mode", payload.mode,
            ]
            if payload.mode == "timed":
                command += ["--due-at", str(payload.due_at)]
            outputs[account] = _last_json(_run(
                command,
                cwd=config.g3_root,
                env_file=config.g3_env_file,
                timeout=config.stage_timeout,
                log_path=asset_root / "logs" / "g3_manual_schedule.log",
            ))
        except Exception as exc:
            errors[account] = f"{type(exc).__name__}: {exc}"
    if len(errors) == len(accounts):
        failed_metadata = dict(post.get("metadata") or {})
        failed_metadata["buffer_status"] = "failed"
        failed_metadata["buffer_error"] = "; ".join(f"{name}: {error}" for name, error in errors.items())
        update_manual_post(post_record_id, metadata_json=json.dumps(failed_metadata, ensure_ascii=False))
        raise HTTPException(502, f"manual Buffer scheduling failed: {failed_metadata['buffer_error']}")
    scheduled_ids: list[str] = []
    for output in outputs.values():
        results = output.get("results") if isinstance(output, dict) else []
        scheduled_ids.extend(str(item.get("post_id")) for item in results if isinstance(item, dict) and item.get("post_id"))
    completed_metadata = dict((get_manual_post(post_record_id) or post).get("metadata") or {})
    completed_metadata["buffer_status"] = "scheduled"
    completed_metadata["buffer_accounts"] = accounts
    completed_metadata["buffer_account"] = accounts[0]
    completed_metadata["buffer_schedule_mode"] = payload.mode
    completed_metadata["buffer_scheduled_at"] = str(payload.due_at) if payload.mode == "timed" else None
    completed_metadata["buffer_post_ids"] = scheduled_ids
    completed_metadata["buffer_result"] = outputs
    if errors:
        completed_metadata["buffer_error"] = "; ".join(f"{name}: {error}" for name, error in errors.items())
    else:
        completed_metadata.pop("buffer_error", None)
    completed_metadata["workflow_status"] = "scheduled"
    updated = update_manual_post(post_record_id, metadata_json=json.dumps(completed_metadata, ensure_ascii=False))
    record_usage(org_id, "publishes", f"{post_record_id}:{','.join(scheduled_ids) or '-'}")
    when = f" for {payload.due_at}" if payload.mode == "timed" else " in the Buffer queue"
    names = ", ".join(accounts)
    return {"ok": True, "post": _public_manual_post(updated), "result": outputs, "message": f"Buffer post scheduled{when} (accounts: {names})."}


@router.get("/orgs")
def marketing_orgs():
    from core.state import get_org, get_org_capabilities, list_orgs
    from engines.g3.g3_runtime.accounts import list_accounts

    scoped = _scoped_org_id()
    env_accounts = [] if scoped and (get_org(scoped) or {}).get("plan") == "free" else list_accounts()
    orgs = []
    for org in ([get_org(scoped)] if scoped else list_orgs()):
        if not org:
            continue
        prefix = (org.get("env_prefix") or "BUFFER_").upper()
        accounts = []
        for acct in env_accounts:
            acct_name = acct["name"]
            if acct_name == "default":
                acct_prefix = "BUFFER_"
            else:
                acct_prefix = f"BUFFER_{acct_name.upper().replace('-', '_')}_"
            if acct_prefix != prefix:
                continue
            platforms = sorted(
                p for p, v in [("instagram", acct.get("instagram_channel_id")), ("x", acct.get("x_channel_id"))]
                if v
            )
            if os.environ.get(f"{acct_prefix}LINKEDIN_CHANNEL_ID", "").strip():
                platforms.append("linkedin")
            accounts.append({"name": acct_name, "platforms": platforms})
        platforms = sorted({p for a in accounts for p in a["platforms"]})
        orgs.append({
            **{key: org.get(key) for key in ("id", "name", "slug", "domain", "status")},
            "capabilities": get_org_capabilities(org["id"]),
            "platforms": platforms,
            "accounts": accounts,
        })
    return {"orgs": orgs}


class MarketingOrgCreateRequest(BaseModel):
    model_config = {"env_prefix": "BUFFER_"}

    name: str = Field(min_length=1, max_length=120)
    slug: str | None = Field(default=None, max_length=60)
    domain: str = Field(default="", max_length=253)
    capabilities: dict[str, bool] = Field(default_factory=dict)


@router.post("/orgs", response_model=MarketingOrgCreateResult)
def create_marketing_org(payload: MarketingOrgCreateRequest):
    if _scoped_org_id():
        raise HTTPException(403, "additional organizations are not available on this account")
    import re
    from core.state import (
        create_org,
        set_active_org,
        get_org_by_slug,
        set_org_capabilities,
        get_org_capabilities,
        VALID_CAPABILITIES,
    )

    slug = (payload.slug or "").strip().lower()
    if not slug:
        slug = re.sub(r"[^a-z0-9]+", "-", payload.name.lower().strip())[:60].strip("-")
    if not slug:
        raise HTTPException(422, "slug is required")
    domain = (payload.domain or "").strip().lower().removeprefix("https://").removeprefix("http://").split("/")[0].lstrip("www.")
    for capability in payload.capabilities:
        if capability not in VALID_CAPABILITIES:
            raise HTTPException(422, f"unknown capability: {capability}")
    existing = get_org_by_slug(slug)
    if existing:
        raise HTTPException(409, f"org '{slug}' already exists")
    org = create_org(payload.name.strip(), slug, domain=domain)
    capabilities = set_org_capabilities(org["id"], payload.capabilities) if payload.capabilities else {}
    from engines.g3.g3_runtime.accounts import list_accounts
    env_accounts = list_accounts()
    prefix = (org.get("env_prefix") or "BUFFER_").upper()
    accounts = []
    for acct in env_accounts:
        acct_name = acct["name"]
        if acct_name == "default":
            acct_prefix = "BUFFER_"
        else:
            acct_prefix = f"BUFFER_{acct_name.upper().replace('-', '_')}_"
        if acct_prefix == prefix:
            accounts.append({
                "name": acct_name,
                "platforms": sorted(
                    p for p, v in [("instagram", acct.get("instagram_channel_id")), ("x", acct.get("x_channel_id"))]
                    if v
                ),
            })
    return {
        "ok": True,
        "org": {
            **{key: org.get(key) for key in ("id", "name", "slug", "domain", "status")},
            "capabilities": capabilities,
            "accounts": accounts,
        },
    }


class OrgCapabilitiesRequest(BaseModel):
    capabilities: dict[str, bool]


@router.get("/orgs/{org_id}/capabilities")
def get_org_capabilities_route(org_id: int):
    from core.state import get_org, get_org_capabilities

    _ensure_org_scope(org_id)
    if not get_org(org_id):
        raise HTTPException(404, "org not found")
    return {"org_id": org_id, "capabilities": get_org_capabilities(org_id)}


@router.post("/orgs/{org_id}/capabilities", response_model=OrgCapabilitiesResult)
def set_org_capabilities_route(org_id: int, payload: OrgCapabilitiesRequest):
    from core.state import get_org, set_org_capabilities, VALID_CAPABILITIES

    _ensure_org_scope(org_id)
    if not get_org(org_id):
        raise HTTPException(404, "org not found")
    try:
        capabilities = set_org_capabilities(org_id, payload.capabilities)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return {"org_id": org_id, "capabilities": capabilities}


@router.post("/orgs/active", response_model=MarketingOrgActiveResult)
def set_active(payload: ManualPostOrgRequest):
    from core.state import get_org, set_active_org

    _ensure_org_scope(payload.org_id)
    org = get_org(payload.org_id)
    if not org:
        raise HTTPException(404, "org not found")
    set_active_org(org["id"])
    return {"ok": True, "org": {key: org.get(key) for key in ("id", "name", "slug", "status")}}


class ManualPostOrgRequest(BaseModel):
    org_id: int = Field(ge=1)


@router.post("/manual-posts/{post_record_id}/org")
def assign_manual_post_org(post_record_id: str, payload: ManualPostOrgRequest):
    from core.state import get_org

    post = get_manual_post(post_record_id)
    if not post:
        raise HTTPException(404, "manual post not found")
    _ensure_org_scope(int(post.get("org_id") or 0))
    _ensure_org_scope(payload.org_id)
    org = get_org(payload.org_id)
    if not org:
        raise HTTPException(404, "org not found")
    # Logical assignment only: media files stay in their current asset_dir,
    # which the Buffer handoff resolves by absolute path.
    updated = update_manual_post(post_record_id, org_id=org["id"])
    return {"ok": True, "post": _public_manual_post(updated),
            "message": f"Post assigned to org {org['slug']}."}


AI_CAPTION_MAX_SLIDES = 6
AI_CAPTION_MAX_DIM = 768


def _slide_data_uris(post: dict) -> list[str]:
    metadata = post.get("metadata") or {}
    if str(metadata.get("post_type") or "carousel") == "video":
        raise HTTPException(422, "AI title/bio reads slide images; video posts keep their manual caption")
    assets = [dict(item) for item in (post.get("assets") or [])]
    if not assets:
        raise HTTPException(422, "upload slide images before generating AI title/bio")
    asset_dir = Path(str(post.get("asset_dir") or "")).resolve()
    try:
        asset_dir.relative_to(PROJECTS_ROOT)
    except ValueError as exc:
        raise HTTPException(403, "asset path is outside the company workspace") from exc
    uris: list[str] = []
    for asset in assets[:AI_CAPTION_MAX_SLIDES]:
        filename = str(asset.get("filename") or "").strip()
        if Path(filename).suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            continue
        path = (asset_dir / filename).resolve()
        try:
            path.relative_to(asset_dir)
        except ValueError:
            continue
        if not path.is_file():
            continue
        try:
            with Image.open(path) as image:
                frame = image.convert("RGB")
                frame.thumbnail((AI_CAPTION_MAX_DIM, AI_CAPTION_MAX_DIM))
                buffer = io.BytesIO()
                frame.save(buffer, "JPEG", quality=70, optimize=True)
        except Exception as exc:
            raise HTTPException(422, f"unreadable slide image {filename}: {exc}") from exc
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        uris.append(f"data:image/jpeg;base64,{encoded}")
    if not uris:
        raise HTTPException(422, "no readable slide images found for AI title/bio")
    return uris


def _ai_title_bio_from_slides(platform: str, images: list[str], link_label: str, tracked_url: str) -> dict:
    base_url = os.getenv("OMNIROUTE_BASE_URL", "http://127.0.0.1:20128/v1").rstrip("/")
    api_key = os.getenv("OMNIROUTE_API_KEY", "").strip()
    model = os.getenv("MODEL_VISION", "auto/best-vision").strip() or "auto/best-vision"
    if not api_key:
        raise HTTPException(409, "set OMNIROUTE_API_KEY in .env before generating AI title/bio")
    prompt = (
        f"You write social copy for a {platform} post. Read the attached carousel slides and return "
        f"exactly one JSON object with keys 'title' (max 60 chars, plain headline of what the slides show) "
        f"and 'caption' (3 short lines summarizing the slides plus one final CTA line). "
        f"CTA line must be 'Link in bio - {link_label}' for instagram or "
        f"'Get the {link_label}: {tracked_url}' otherwise. "
        f"Describe only what is visible; never invent brand names, metrics, or claims."
    )
    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    content.extend({"type": "image_url", "image_url": {"url": uri}} for uri in images)
    payload = {"model": model, "messages": [{"role": "user", "content": content}],
               "response_format": {"type": "json_object"}, "temperature": 0.4,
               "max_tokens": 600, "stream": False}
    request = urllib.request.Request(
        base_url + "/chat/completions", data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            body = json.loads(response.read().decode("utf-8", errors="replace"))
    except Exception as exc:
        raise HTTPException(502, f"vision model request failed: {type(exc).__name__}: {exc}") from exc
    choices = body.get("choices") or []
    text = ((choices[0].get("message") or {}).get("content") or "") if choices else ""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()[1:]
        if lines and lines[-1].strip() == "```":
            lines.pop()
        text = "\n".join(lines).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise HTTPException(502, f"vision model returned non-JSON copy: {text[:200]!r}") from exc
    title = str(data.get("title") or "").strip()[:80]
    caption = str(data.get("caption") or "").strip()[:2000]
    if not title or not caption:
        raise HTTPException(502, "vision model returned an empty title or caption")
    return {"title": title, "caption": caption}


@router.post("/manual-posts/{post_record_id}/ai-caption")
def generate_manual_post_ai_caption(post_record_id: str):
    post = get_manual_post(post_record_id)
    if not post:
        raise HTTPException(404, "manual post not found")
    platform = str(post.get("platform") or "instagram").strip().lower() or "instagram"
    metadata = dict(post.get("metadata") or {})
    images = _slide_data_uris(post)
    result = _ai_title_bio_from_slides(
        platform, images,
        link_label=str(metadata.get("link_label") or "ops audit"),
        tracked_url=str(post.get("tracked_url") or ""),
    )
    metadata.update({
        "generated_title": result["title"],
        "generated_caption": result["caption"],
        "ai_caption_slides": len(images),
    })
    updated = update_manual_post(
        post_record_id,
        title=result["title"],
        metadata_json=json.dumps(metadata, ensure_ascii=False),
    )
    return {"ok": True, "post": _public_manual_post(updated), "result": result,
            "message": f"AI title/bio generated from {len(images)} slides."}


@router.get("/manual-posts")
def manual_posts(limit: int = 50):
    from core.state import get_active_org

    org = get_active_org()
    org_id = org["id"] if org else None
    return {"posts": [_public_manual_post(item) for item in list_manual_posts(limit=limit, org_id=org_id)]}


@router.get("/manual-posts/{post_record_id}/assets/{asset_index}")
def manual_post_asset(post_record_id: str, asset_index: int):
    post = get_manual_post(post_record_id)
    if not post:
        raise HTTPException(404, "manual post not found")
    assets = post.get("assets") or []
    if asset_index < 0 or asset_index >= len(assets):
        raise HTTPException(404, "asset not found")
    asset = assets[asset_index]
    asset_path = (Path(post.get("asset_dir") or "") / str(asset.get("filename") or "")).resolve()
    try:
        asset_path.relative_to(PROJECTS_ROOT)
    except ValueError as exc:
        raise HTTPException(403, "asset path is outside the company workspace") from exc
    if not asset_path.is_file():
        raise HTTPException(404, "asset file not found")
    return FileResponse(asset_path, media_type=str(asset.get("content_type") or "application/octet-stream"))


