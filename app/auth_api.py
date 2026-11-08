"""Public website auth API: signup, verification, login, logout, session."""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.ratelimit import rate_limit_auth
from core import auth, auth_context
from services.auth_email import dev_token_visible

router = APIRouter(prefix="/api/auth", tags=["auth"])


def session_cookie_name() -> str:
    return os.getenv("AUTH_COOKIE_NAME", "autoevolve_session").strip() or "autoevolve_session"


SESSION_COOKIE = session_cookie_name()


def _cookie_domain() -> str | None:
    value = os.getenv("AUTH_COOKIE_DOMAIN", "").strip()
    return value or None


def _same_site() -> str:
    value = os.getenv("AUTH_COOKIE_SAMESITE", "lax").strip().lower()
    return value if value in {"lax", "strict", "none"} else "lax"


class SignupPayload(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=10, max_length=256)
    company_name: str = Field(default="", max_length=120)


class LoginPayload(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class VerifyPayload(BaseModel):
    token: str = Field(min_length=10, max_length=512)


class ResendPayload(BaseModel):
    email: str = Field(min_length=3, max_length=254)


def _cookie_secure(request: Request) -> bool:
    setting = os.getenv("AUTH_COOKIE_SECURE", "").strip().lower()
    if setting in {"1", "true", "yes"}:
        return True
    if setting in {"0", "false", "no"}:
        return False
    return request.url.scheme == "https"


def _cookie_kwargs(request: Request) -> dict:
    return {
        "path": "/",
        "httponly": True,
        "secure": _cookie_secure(request),
        "samesite": _same_site(),
        **({"domain": _cookie_domain()} if _cookie_domain() else {}),
    }


def _set_session(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        session_cookie_name(),
        token,
        max_age=60 * 60 * 24 * auth.auth_store.SESSION_TTL_DAYS,
        **_cookie_kwargs(request),
    )


def clear_session_cookie(response: Response, request: Request) -> None:
    response.delete_cookie(session_cookie_name(), **_cookie_kwargs(request))


def _clear_session(response: Response, request: Request) -> None:
    clear_session_cookie(response, request)


def _session_payload(result: auth.SessionResult) -> dict:
    return {
        "ok": True,
        "user": auth.public_user(result.user),
        "org": auth.public_org(result.org),
        "expires_at": result.session["expires_at"],
    }


@router.post("/signup", dependencies=[Depends(rate_limit_auth)])
def signup(payload: SignupPayload, request: Request):
    if os.getenv("AUTH_SIGNUP_ENABLED", "true").strip().lower() in {"0", "false", "no"}:
        raise HTTPException(403, "Signups are currently closed.")
    try:
        result = auth.signup(payload.email, payload.password, payload.company_name)
    except auth.AuthError as exc:
        raise HTTPException(exc.status, exc.message) from exc
    body = {
        "ok": True,
        "verification_required": True,
        "email_delivered": result.email.delivered,
        "message": result.email.detail,
        "org": auth.public_org(result.org),
    }
    if dev_token_visible():
        from services.auth_email import verify_url

        body["dev_token"] = result.verification_token
        body["verify_url"] = verify_url(result.verification_token)
    return body


@router.post("/login", dependencies=[Depends(rate_limit_auth)])
def login(payload: LoginPayload, request: Request, response: Response):
    try:
        result = auth.login(payload.email, payload.password)
    except auth.AuthError as exc:
        raise HTTPException(exc.status, exc.message) from exc
    _set_session(response, request, result.token)
    return _session_payload(result)


@router.post("/verify", dependencies=[Depends(rate_limit_auth)])
def verify(payload: VerifyPayload, request: Request, response: Response):
    try:
        result = auth.verify_email(payload.token)
    except auth.AuthError as exc:
        raise HTTPException(exc.status, exc.message) from exc
    _set_session(response, request, result.token)
    return _session_payload(result)


@router.post("/resend", dependencies=[Depends(rate_limit_auth)])
def resend(payload: ResendPayload):
    result = auth.resend_verification(payload.email)
    body = {"ok": True, "message": result.detail}
    if dev_token_visible() and result.token:
        from services.auth_email import verify_url

        body["dev_token"] = result.token
        body["verify_url"] = verify_url(result.token)
    return body


@router.post("/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(session_cookie_name())
    if token:
        auth.auth_store.delete_session(token)
    _clear_session(response, request)
    return {"ok": True}


@router.get("/me")
def me():
    user_id = auth_context.current_user_id.get()
    org_id = auth_context.current_org_id.get()
    if not user_id or not org_id:
        raise HTTPException(401, "Not authenticated")
    return auth.me(user_id, int(org_id), auth_context.current_session_hash.get())
