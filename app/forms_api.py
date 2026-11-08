"""Custom lead forms: hosted pages, external submissions, booking links.

A form is a slug plus fields (core.form_store). It can be filled in two ways
that land in exactly the same place:

1. The hosted page at /f/{slug} — branded, mobile-clean, no extra service.
2. Any external tool (an indataflow form, a generic POSTing service) that
   submits to /integrations/leads/form with the form slug.

Both write a lead through the existing upsert path plus an inbound 'form'
interaction, so the submission appears in Replies as a clean question/answer
list with the same founder actions as an email reply.

Nothing here sends email. The only send is the founder's explicit
POST /company/sales/leads/{id}/meeting-request, which mails the contact a
booking page; the contact choosing a time on /book/{id} is what records the
scheduled meeting.
"""
from __future__ import annotations

import hmac
import json
import os
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator

from app.ratelimit import rate_limit_intake
from app.sales_api import verify_founder_action
from core import form_store, sales_store
from core.branding import company_logo_url, company_name, company_public_url

templates = Jinja2Templates(directory="templates")
templates.env.globals.update(company_name=company_name(), company_logo_url=company_logo_url())

# Public pages and intake: never dashboard-authenticated. Submission routes
# carry their own rate limit; the GET pages do not need one.
public_router = APIRouter(tags=["forms-public"])
intake_router = APIRouter(prefix="/integrations", tags=["integrations"])
router = APIRouter(prefix="/company/commercial/forms", tags=["forms"])


def _page_context(request: Request) -> dict[str, Any]:
    return {"request": request, "company_name": company_name(), "company_logo_url": company_logo_url()}


def _check_optional_intake_secret(value: str | None) -> None:
    """Enforce the shared intake secret only when it is configured: the
    hosted page has no secret (it is a public form), and an unset secret on a
    self-hosted instance must not brick the endpoint."""
    expected = os.getenv("SALES_INTAKE_SECRET", "").strip()
    if expected and (not value or not hmac.compare_digest(value, expected)):
        raise HTTPException(401, "invalid lead intake credential")


def _record_submission(
    form: dict[str, Any] | None,
    answers: dict[str, Any],
    *,
    source_detail: str,
) -> dict[str, Any]:
    lead_payload, clean_answers = form_store.map_answers_to_lead(form, answers)
    if not lead_payload.get("email") and not lead_payload.get("phone"):
        raise HTTPException(422, "email or phone is required")
    lead_payload["source"] = "form"
    lead_payload["source_detail"] = source_detail
    lead_payload["consent"] = bool(lead_payload.get("consent"))
    lead, created = sales_store.upsert_lead(lead_payload)
    body = "\n".join(f"{label}: {value}" for label, value in clean_answers.items()) or "No answers were recorded."
    sales_store.add_interaction(
        lead["id"],
        "inbound",
        "form",
        "submission",
        form["name"] if form else "Form submission",
        body,
        metadata={
            "form_slug": form["slug"] if form else None,
            "form_name": form["name"] if form else None,
            "answers": clean_answers,
        },
    )
    return {"lead_id": lead["id"], "created": created, "stage": lead["stage"]}


# ---------------------------------------------------------------- public pages


@public_router.get("/f/{slug}", response_class=HTMLResponse)
def hosted_form(slug: str, request: Request, sent: int = 0):
    form = form_store.get_form(slug)
    if not form or not form["active"]:
        raise HTTPException(404, "form not found")
    return templates.TemplateResponse(
        request,
        name="form.html",
        context={**_page_context(request), "form": form, "sent": bool(sent),
                 "error": None, "values": {}},
    )


@public_router.post("/f/{slug}", response_class=HTMLResponse, dependencies=[Depends(rate_limit_intake)])
async def hosted_form_submit(slug: str, request: Request):
    form = form_store.get_form(slug)
    if not form or not form["active"]:
        raise HTTPException(404, "form not found")
    submitted = await request.form()
    answers = {key: value for key, value in submitted.items() if key != "website"}
    # Honeypot: a filled hidden field is a bot. Answer like success, write nothing.
    if str(submitted.get("website") or "").strip():
        return RedirectResponse(f"/f/{slug}?sent=1", status_code=303)
    try:
        _record_submission(form, answers, source_detail=f"hosted form {slug}")
    except HTTPException as exc:
        if exc.status_code != 422:
            raise
        return templates.TemplateResponse(
            request,
            name="form.html",
            context={**_page_context(request), "form": form, "sent": False,
                     "error": exc.detail, "values": answers},
        )
    return RedirectResponse(f"/f/{slug}?sent=1", status_code=303)


@public_router.get("/book/{lead_id}", response_class=HTMLResponse)
def booking_page(lead_id: str, request: Request):
    lead = sales_store.get_lead(lead_id)
    meeting = (lead.get("metadata") or {}).get("meeting") if lead else None
    slots = (meeting or {}).get("slots") or []
    context = {**_page_context(request), "lead_id": lead_id, "slots": slots,
               "note": (meeting or {}).get("note"), "confirmed": None, "already": None, "error": None}
    if not lead or not meeting:
        context["error"] = "This booking link is not valid. Reply to the email you received and we will resend it."
    elif meeting.get("status") == "scheduled":
        context["already"] = f"This meeting is already held for {meeting.get('scheduled_for')}."
    elif not slots:
        context["error"] = "No times are currently offered on this link. Reply to the email you received and we will sort out a time."
    return templates.TemplateResponse(request, name="book.html", context=context)


@public_router.post("/book/{lead_id}", response_class=HTMLResponse, dependencies=[Depends(rate_limit_intake)])
async def booking_confirm(lead_id: str, request: Request):
    submitted = await request.form()
    lead = sales_store.get_lead(lead_id)
    meeting = (lead.get("metadata") or {}).get("meeting") if lead else None
    slots = (meeting or {}).get("slots") or []
    base = {**_page_context(request), "lead_id": lead_id, "slots": slots,
            "note": (meeting or {}).get("note"), "confirmed": None, "already": None, "error": None}
    if not lead or not meeting:
        base["error"] = "This booking link is not valid."
        return templates.TemplateResponse(request, name="book.html", context=base)
    if meeting.get("status") == "scheduled":
        base["already"] = f"This meeting is already held for {meeting.get('scheduled_for')}."
        return templates.TemplateResponse(request, name="book.html", context=base)
    raw = str(submitted.get("slot") or "").strip()
    if not raw.isdigit() or int(raw) >= len(slots):
        base["error"] = "That time is not on this offer. Pick one of the times listed."
        return templates.TemplateResponse(request, name="book.html", context=base)
    chosen = slots[int(raw)]
    sales_store.mark_meeting_scheduled(
        lead_id, scheduled_for=chosen, note=meeting.get("note"), source="booking_link",
    )
    base["confirmed"] = chosen
    return templates.TemplateResponse(request, name="book.html", context=base)


# ------------------------------------------------------------ external intake


@intake_router.post("/leads/form", dependencies=[Depends(rate_limit_intake)])
async def external_form_intake(
    request: Request,
    x_company_core_lead_secret: str | None = Header(
        default=None, alias="X-Company-Core-Lead-Secret",
    ),
):
    """Shared submission endpoint for external form tools.

    Accepts JSON ({"form": "contact", "answers": {...}}, a flat object of
    answers, or a flat object with a "form" key) or form-encoded bodies.
    Known keys map onto the lead record; everything else is kept as clean
    answers on the inbound interaction.
    """
    _check_optional_intake_secret(x_company_core_lead_secret)
    content_type = request.headers.get("content-type", "")
    if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
        submitted = await request.form()
        answers = {key: value for key, value in submitted.items()}
        slug = str(answers.pop("form", "") or "").strip().lower() or None
    else:
        try:
            raw = json.loads(await request.body())
        except json.JSONDecodeError as exc:
            raise HTTPException(422, "invalid form JSON payload") from exc
        if not isinstance(raw, dict):
            raise HTTPException(422, "form payload must be a JSON object")
        slug = str(raw.get("form") or "").strip().lower() or None
        nested = raw.get("answers")
        answers = dict(nested) if isinstance(nested, dict) else {
            key: value for key, value in raw.items() if key not in {"form", "website"}
        }
    form = form_store.get_form(slug) if slug else None
    if slug and not form:
        raise HTTPException(404, "form not found")
    result = _record_submission(
        form, answers, source_detail=f"external form {form['slug']}" if form else "external form",
    )
    return {"ok": True, "lead_id": result["lead_id"], "created": result["created"],
            "stage": result["stage"], "form": form["slug"] if form else None}


# ---------------------------------------------------------- form management


class FormFieldPayload(BaseModel):
    key: str
    label: str
    type: str = "text"
    required: bool = False
    options: list[str] | None = None


class FormCreatePayload(BaseModel):
    slug: str
    name: str
    description: str | None = None
    fields: list[FormFieldPayload]


class FormUpdatePayload(BaseModel):
    name: str | None = None
    description: str | None = None
    fields: list[FormFieldPayload] | None = None
    active: bool | None = None


def _form_view(form: dict[str, Any]) -> dict[str, Any]:
    return {
        **form,
        "hosted_path": f"/f/{form['slug']}",
        "external_endpoint": "/integrations/leads/form",
    }


@router.get("/config")
def intake_config() -> dict[str, Any]:
    """Everything an external form tool needs, on one screen.

    The endpoint URL is built from COMPANY_PUBLIC_URL (the address the tool
    must reach), not the browser origin: the founder may be viewing the
    dashboard on a LAN address the outside world cannot use. The secret is
    only ever read from the environment — there is no other copy of it.
    """
    secret = os.getenv("SALES_INTAKE_SECRET", "").strip()
    return {
        "endpoint_url": f"{company_public_url()}/integrations/leads/form",
        "secret_header": "X-Company-Core-Lead-Secret",
        "secret": secret or None,
        "secret_configured": bool(secret),
    }


@router.get("")
def list_forms():
    return [_form_view(form) for form in form_store.list_forms()]


@router.post("", dependencies=[Depends(verify_founder_action)])
def create_form(payload: FormCreatePayload):
    try:
        form = form_store.create_form(
            payload.slug,
            payload.name,
            [field.model_dump(exclude_none=True) for field in payload.fields],
            payload.description,
        )
    except ValueError as exc:
        raise HTTPException(409 if "slug" in str(exc) else 422, str(exc)) from exc
    return _form_view(form)


@router.patch("/{slug}", dependencies=[Depends(verify_founder_action)])
def update_form(slug: str, payload: FormUpdatePayload):
    try:
        form = form_store.update_form(
            slug,
            name=payload.name,
            description=payload.description,
            fields=[field.model_dump(exclude_none=True) for field in payload.fields] if payload.fields is not None else None,
            active=payload.active,
        )
    except ValueError as exc:
        raise HTTPException(404 if "not found" in str(exc) else 422, str(exc)) from exc
    return _form_view(form)
