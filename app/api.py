from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Request,
)
import os
from pathlib import Path
from urllib.parse import urlparse

from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.ratelimit import rate_limit_intake
from app.security import authenticate, require_operator
from app.auth_api import clear_session_cookie, router as auth_router, session_cookie_name
from core.auth import resolve_session
from core.auth_context import bind_session, reset_session
from app.contacts_api import router as contacts_router
from app.companies_api import router as companies_router
from app.workspace_api import router as workspace_router
from app.workflow_views_api import router as workflow_views_router
from core.branding import company_logo_url, company_name


def _on_startup():
    from dotenv import load_dotenv
    g3_env = os.path.join(os.path.dirname(os.path.dirname(__file__)), "engines", "g3", "config", "g3.env")
    if os.path.exists(g3_env):
        load_dotenv(g3_env, override=False)
    from core.bootstrap import init_all_schema

    init_all_schema()
    from core.state import _seed_orgs_from_env
    if os.getenv("BOOTSTRAP_LEGACY_ORGS", "false").strip().lower() in {"1", "true", "yes"}:
        _seed_orgs_from_env()
    _reconcile_stranded_sends()


def _reconcile_stranded_sends():
    """Recover drafts left in 'sending' by a crash or restart.

    Inside the provider idempotency window the same key is retried; older
    attempts are parked in send_unknown for an operator. Never block boot.
    """
    enabled = os.getenv("SALES_SEND_RECONCILE_ON_STARTUP", "true").strip().lower()
    if enabled in {"0", "false", "no"}:
        return
    try:
        from services.sales_service import reconcile_sending_drafts

        report = reconcile_sending_drafts()
    except Exception as exc:  # noqa: BLE001 - recovery must not stop the API
        print(f"[startup] send reconciliation failed: {exc}")
        return
    if report["scanned"]:
        print(f"[startup] send reconciliation: {report}")


app = FastAPI(
    title="Company Cockpit",
)

_ASSET_PREFIX = "/assets/"

# Defence in depth for a dashboard that renders tenant data. Scripts stay
# same-origin (the bundle is the only script); images and media may come from
# object storage over https; inline styles are required by React.
_CONTENT_SECURITY_POLICY = "; ".join((
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob: https:",
    "media-src 'self' blob: https:",
    "connect-src 'self'",
    "font-src 'self' data:",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
))


@app.middleware("http")
async def website_session(request: Request, call_next):
    """Bind a verified website session to this request's org.

    Legacy Basic-auth requests have no cookie and fall through to the global
    active-org setting exactly as before.
    """
    if request.url.path.startswith(("/assets/", "/site-assets/", "/static/")):
        return await call_next(request)
    # Basic auth remains an explicit operator/legacy choice even if a website
    # cookie happens to be present in the same browser.
    if request.headers.get("authorization"):
        return await call_next(request)
    token = request.cookies.get(session_cookie_name())
    resolved = resolve_session(token) if token else None
    context_tokens = None
    if resolved:
        user, org, session = resolved
        context_tokens = bind_session(
            user_id=user["id"], org_id=int(org["id"]), session_hash=session["token_hash"]
        )
        request.state.auth_user = user
        request.state.auth_org = org
    # Cookie-authenticated mutations are same-site by default. Requiring an
    # explicit Origin allow-list closes the sibling-subdomain gap that
    # SameSite=Lax does not cover.
    unsafe = request.method in {"POST", "PUT", "PATCH", "DELETE"}
    if unsafe and (resolved or request.url.path.startswith("/api/auth/")):
        origin = (request.headers.get("origin") or "").rstrip("/")
        allowed = {
            item.strip().rstrip("/")
            for item in os.getenv("AUTH_ALLOWED_ORIGINS", "").split(",")
            if item.strip()
        }
        if origin and allowed and origin not in allowed:
            if context_tokens:
                reset_session(context_tokens)
            return JSONResponse({"detail": "origin is not allowed for this action"}, status_code=403)
    try:
        response = await call_next(request)
    finally:
        if context_tokens:
            reset_session(context_tokens)
    if token and not resolved and "set-cookie" not in response.headers:
        clear_session_cookie(response, request)
    return response


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    headers = response.headers
    headers.setdefault("Content-Security-Policy", _CONTENT_SECURITY_POLICY)
    headers.setdefault("X-Content-Type-Options", "nosniff")
    headers.setdefault("X-Frame-Options", "DENY")
    headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    return response


@app.middleware("http")
async def cache_headers(request: Request, call_next):
    """Cache policy stated by the app, not only by the proxy.

    Hashed Vite bundles are the only public, year-long cache here: their names
    change when their bytes change. Everything else is tenant data or the SPA
    shell that must point at the newest bundle, so it is explicitly
    ``no-store``. A proxy or CDN can then only make things faster, never show
    one company's numbers to another or a stale send count to its owner.
    """
    response = await call_next(request)
    if request.url.path.startswith(_ASSET_PREFIX):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif "cache-control" not in response.headers:
        response.headers["Cache-Control"] = "no-store"
    return response


@app.on_event("startup")
def _startup():
    _on_startup()

app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static",
)

templates = Jinja2Templates(
    directory="templates"
)
templates.env.globals.update(
    company_name=company_name(),
    company_logo_url=company_logo_url(),
)


def _calendar_base_url() -> str:
    return (
        os.getenv("SALES_CALENDAR_BASE_URL", "http://localhost:3000").strip()
        or "http://localhost:3000"
    ).rstrip("/")


def _calendar_event_path() -> str:
    raw = os.getenv("SALES_CALENDAR_EVENT_PATH", "book/company").strip() or "book/company"
    return raw if raw.startswith("/") else f"/{raw}"


def _calendar_expand_target(value: str | None) -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None
    parsed = urlparse(raw)
    path = (parsed.path or "").rstrip("/")
    if parsed.scheme and parsed.netloc and path not in {"", "/"}:
        return raw
    if parsed.scheme and parsed.netloc:
        return f"{raw.rstrip('/')}{_calendar_event_path()}"
    return raw


def _calendar_booking_url() -> str:
    override = _calendar_expand_target(os.getenv("SALES_CALENDAR_BOOKING_URL", ""))
    if override:
        return override
    return f"{_calendar_base_url()}{_calendar_event_path()}"


def _calendar_embed_url() -> str | None:
    embed = _calendar_expand_target(os.getenv("SALES_CALENDAR_EMBED_URL", ""))
    if embed:
        return embed
    return _calendar_booking_url()


def _ui_redirect(request: Request, destination: str, *, status_code: int = 307):
    # Preserve shareable filters and selections when following an old bookmark.
    query = request.url.query
    return RedirectResponse(f"{destination}?{query}" if query else destination, status_code=status_code)


@app.get("/", include_in_schema=False)
def home(request: Request):
    return _ui_redirect(request, "/home")


@app.get("/legacy/operations", include_in_schema=False)
def operations(request: Request):
    return _ui_redirect(request, "/home")


@app.get("/operations/sales", include_in_schema=False)
@app.get("/operations/sales/discovery", include_in_schema=False)
def operations_sales(request: Request):
    return _ui_redirect(request, "/research")


@app.get("/legacy/operations/sales/email", include_in_schema=False)
def operations_sales_email(request: Request):
    return _ui_redirect(request, "/outreach")


@app.get("/legacy/operations/marketing", include_in_schema=False)
@app.get("/legacy/operations/marketing/campaigns", include_in_schema=False)
def operations_marketing(request: Request):
    return _ui_redirect(request, "/content")


@app.get("/legacy/operations/marketing/assets", include_in_schema=False)
def operations_marketing_assets(request: Request):
    return _ui_redirect(request, "/content")


@app.get("/operations", include_in_schema=False)
def modern_operations(request: Request):
    return _ui_redirect(request, "/home")


@app.get("/operations/sales/email", include_in_schema=False)
def modern_outreach(request: Request):
    return _ui_redirect(request, "/outreach")


@app.get("/operations/marketing", include_in_schema=False)
@app.get("/operations/marketing/campaigns", include_in_schema=False)
def modern_campaigns(request: Request):
    return _ui_redirect(request, "/content")


@app.get("/operations/marketing/assets", include_in_schema=False)
def modern_content(request: Request):
    return _ui_redirect(request, "/content")


@app.get("/operations/marketing/publishing", include_in_schema=False)
def operations_marketing_publishing(request: Request):
    return _ui_redirect(request, "/content")


@app.get("/operations/history", include_in_schema=False)
def operations_history(request: Request):
    return _ui_redirect(request, "/home")


@app.get(
    "/meet",
    response_class=HTMLResponse,
)
async def meet(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="meet.html",
        context={
            "request": request,
            "calendar_page_url": "/calendar",
            "calendar_direct_url": _calendar_booking_url(),
        },
    )


@app.get(
    "/calendar",
    response_class=HTMLResponse,
)
async def calendar_page(request: Request):
    booking_url = _calendar_booking_url()
    return templates.TemplateResponse(
        request=request,
        name="calendar.html",
        context={
            "request": request,
            "calendar_booking_url": booking_url,
            "calendar_embed_url": _calendar_embed_url(),
            "calendar_base_url": _calendar_base_url(),
        },
    )


@app.get("/health")
async def health():
    return {
        "status": "ok",
    }


@app.get("/public/manual-posts/{post_id}/assets/{index}", include_in_schema=False)
def public_manual_post_asset(post_id: str, index: int, exp: int, token: str):
    """Short-lived signed media link for an external webhook scheduler."""
    from services.publishers.webhook import PublisherError, public_asset

    try:
        path, filename, content_type = public_asset(post_id, index, exp, token)
    except PublisherError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    return FileResponse(
        path,
        media_type=content_type,
        filename=filename,
        headers={"Cache-Control": "private, max-age=300"},
    )


from app.company_ops_api import router as company_ops_router
from app.company_context_api import router as company_context_router
from app.forms_api import intake_router as forms_intake_router
from app.forms_api import public_router as forms_public_router
from app.forms_api import router as forms_router
from app.marketing_api import router as marketing_router
from app.validation_api import router as validation_router
from app.validation_api import automation_router as validation_automation_router
from app.workflows_api import router as workflows_router
from app.sales_api import action_router as sales_action_router
from app.sales_api import intake_router as sales_intake_router
from app.sales_api import router as sales_router
from app.commercial_api import oauth_callback_router as commercial_oauth_router
from app.commercial_api import router as commercial_router
from app.setup_api import router as setup_router

app.include_router(auth_router)
app.include_router(company_ops_router, dependencies=[Depends(authenticate), Depends(require_operator)])
app.include_router(company_context_router, dependencies=[Depends(authenticate)])
app.include_router(marketing_router, dependencies=[Depends(authenticate)])
app.include_router(validation_router, dependencies=[Depends(authenticate)])
app.include_router(validation_automation_router, dependencies=[Depends(authenticate)])
app.include_router(sales_router, dependencies=[Depends(authenticate)])
app.include_router(commercial_router, dependencies=[Depends(authenticate)])
# OAuth callbacks carry their own signed-state authentication.
app.include_router(commercial_oauth_router)
app.include_router(contacts_router, dependencies=[Depends(authenticate)])
app.include_router(companies_router, dependencies=[Depends(authenticate)])
app.include_router(workspace_router, dependencies=[Depends(authenticate)])
app.include_router(workflow_views_router, dependencies=[Depends(authenticate)])
app.include_router(workflows_router, dependencies=[Depends(authenticate)])
app.include_router(sales_action_router, dependencies=[Depends(authenticate)])
app.include_router(forms_router, dependencies=[Depends(authenticate), Depends(require_operator)])
app.include_router(setup_router, dependencies=[Depends(authenticate)])
# Tunnel-facing integrations stay outside dashboard auth and enforce their own
# shared-secret checks in app.sales_api. They are rate limited per client IP.
app.include_router(sales_intake_router, dependencies=[Depends(rate_limit_intake)])
app.include_router(forms_intake_router, dependencies=[Depends(rate_limit_intake)])
# Public form pages and booking pages: no dashboard auth, the URLs themselves
# are what a form visitor or an emailed contact holds.
app.include_router(forms_public_router)

# The React client is a static build served by this FastAPI process. API routes
# keep their existing authentication and action gates.
_ui_dist = Path(__file__).resolve().parent.parent / "autoevolve-ui" / "dist"
if _ui_dist.is_dir():
    app.mount("/assets", StaticFiles(directory=_ui_dist / "assets"), name="ui-assets")


@app.get("/contacts", include_in_schema=False)
@app.get("/contacts/", include_in_schema=False)
@app.get("/research", include_in_schema=False)
@app.get("/research/", include_in_schema=False)
@app.get("/companies", include_in_schema=False)
@app.get("/companies/", include_in_schema=False)
@app.get("/integrations", include_in_schema=False)
@app.get("/integrations/", include_in_schema=False)
@app.get("/settings", include_in_schema=False)
@app.get("/settings/", include_in_schema=False)
@app.get("/home", include_in_schema=False)
@app.get("/home/", include_in_schema=False)
@app.get("/outreach", include_in_schema=False)
@app.get("/outreach/", include_in_schema=False)
@app.get("/replies", include_in_schema=False)
@app.get("/replies/", include_in_schema=False)
@app.get("/meetings", include_in_schema=False)
@app.get("/meetings/", include_in_schema=False)
@app.get("/content", include_in_schema=False)
@app.get("/content/", include_in_schema=False)
@app.get("/onboarding", include_in_schema=False)
@app.get("/onboarding/", include_in_schema=False)
@app.get("/commercial", include_in_schema=False)
@app.get("/commercial/", include_in_schema=False)
@app.get("/workflows", include_in_schema=False)
@app.get("/workflows/", include_in_schema=False)
@app.get("/validation", include_in_schema=False)
@app.get("/validation/", include_in_schema=False)
def ui_app(request: Request):
    if request.url.path.endswith("/"):
        return _ui_redirect(request, request.url.path.rstrip("/"), status_code=308)
    if not (_ui_dist / "index.html").is_file():
        raise HTTPException(503, "Frontend has not been built")
    return FileResponse(_ui_dist / "index.html")


@app.get("/{path:path}", include_in_schema=False)
def missing_page(path: str, request: Request):
    # Only browser navigation gets the React not-found screen. Unknown API,
    # asset, and utility paths remain genuine JSON 404s, never SPA success.
    namespace = path.split("/", 1)[0]
    if namespace not in {"company", "assets", "static", "health", "docs", "redoc", "openapi.json"} and "text/html" in request.headers.get("accept", ""):
        if not (_ui_dist / "index.html").is_file():
            raise HTTPException(503, "Frontend has not been built")
        return FileResponse(_ui_dist / "index.html", status_code=404)
    raise HTTPException(404, "Not Found")
