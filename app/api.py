from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Request,
)
import os
from pathlib import Path
from urllib.parse import urlparse

from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.ratelimit import rate_limit_intake
from app.security import authenticate
from app.contacts_api import router as contacts_router
from app.companies_api import router as companies_router
from app.workspace_api import router as workspace_router
from app.workflow_views_api import router as workflow_views_router
from app.onboarding_api import read_router as onboarding_read_router, write_router as onboarding_write_router
from core.branding import company_logo_url, company_name


def _on_startup():
    from dotenv import load_dotenv
    g3_env = os.path.join(os.path.dirname(os.path.dirname(__file__)), "engines", "g3", "config", "g3.env")
    if os.path.exists(g3_env):
        load_dotenv(g3_env, override=False)
    from core.state import init_db, _seed_orgs_from_env
    init_db()
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
    return _ui_redirect(request, "/campaigns")


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
    return _ui_redirect(request, "/campaigns")


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


from app.company_ops_api import router as company_ops_router
from app.marketing_api import router as marketing_router
from app.sales_api import action_router as sales_action_router
from app.sales_api import intake_router as sales_intake_router
from app.sales_api import router as sales_router
from app.setup_api import router as setup_router

app.include_router(company_ops_router, dependencies=[Depends(authenticate)])
app.include_router(marketing_router, dependencies=[Depends(authenticate)])
app.include_router(sales_router, dependencies=[Depends(authenticate)])
app.include_router(contacts_router, dependencies=[Depends(authenticate)])
app.include_router(companies_router, dependencies=[Depends(authenticate)])
app.include_router(workspace_router, dependencies=[Depends(authenticate)])
app.include_router(workflow_views_router, dependencies=[Depends(authenticate)])
app.include_router(onboarding_read_router, dependencies=[Depends(authenticate)])
app.include_router(sales_action_router, dependencies=[Depends(authenticate)])
app.include_router(setup_router, dependencies=[Depends(authenticate)])
app.include_router(onboarding_write_router, dependencies=[Depends(authenticate)])
# Tunnel-facing integrations stay outside dashboard auth and enforce their own
# shared-secret checks in app.sales_api. They are rate limited per client IP.
app.include_router(sales_intake_router, dependencies=[Depends(rate_limit_intake)])

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
@app.get("/campaigns", include_in_schema=False)
@app.get("/campaigns/", include_in_schema=False)
@app.get("/content", include_in_schema=False)
@app.get("/content/", include_in_schema=False)
@app.get("/onboarding", include_in_schema=False)
@app.get("/onboarding/", include_in_schema=False)
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
