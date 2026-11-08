"""Website authentication and free-org provisioning.

The paid dashboard keeps its Basic-auth operator path. Website users get a
password account, a verified email, a free organization, and an HttpOnly
session cookie. The session is resolved on every request by middleware and
binds the request to that organization.
"""
from __future__ import annotations

import re
import secrets
import sqlite3
from dataclasses import dataclass
from typing import Any

from core import auth_store, state
from core.auth_security import hash_password, verify_password
from services.auth_email import AuthEmailResult, send_verification_email

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass
class SignupResult:
    user: dict[str, Any]
    org: dict[str, Any]
    verification_token: str
    email: AuthEmailResult


@dataclass
class SessionResult:
    token: str
    user: dict[str, Any]
    org: dict[str, Any]
    session: dict[str, Any]


def validate_email(email: str) -> str:
    normalized = auth_store.normalize_email(email)
    if not normalized or len(normalized) > 254 or not EMAIL_RE.fullmatch(normalized):
        raise AuthError(422, "Enter a valid work email address.")
    return normalized


def validate_password(password: str) -> str:
    if len(password) < 10:
        raise AuthError(422, "Use at least 10 characters for your password.")
    if len(password) > 256:
        raise AuthError(422, "Password is too long.")
    return password


def _slug(value: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")[:40]
    return base or "workspace"


def _unique_slug(company_name: str) -> str:
    base = _slug(company_name)
    candidate = base
    for _ in range(8):
        if not state.get_org_by_slug(candidate):
            return candidate
        candidate = f"{base}-{secrets.token_hex(3)}"
    return f"{base}-{secrets.token_hex(8)}"


def _env_prefix(slug: str) -> str:
    token = re.sub(r"[^A-Z0-9]+", "_", slug.upper()).strip("_")[:20] or "FREE"
    return f"FREE_{token}_"


def public_user(user: dict[str, Any] | None) -> dict[str, Any] | None:
    if not user:
        return None
    return {
        "id": user["id"],
        "email": user["email"],
        "email_verified": bool(user.get("email_verified_at")),
        "created_at": user.get("created_at"),
    }


def public_org(org: dict[str, Any] | None) -> dict[str, Any] | None:
    if not org:
        return None
    return {
        "id": org["id"],
        "name": org["name"],
        "slug": org["slug"],
        "plan": org.get("plan") or "paid",
        "domain": org.get("domain") or "",
    }


def signup(email: str, password: str, company_name: str = "") -> SignupResult:
    email = validate_email(email)
    validate_password(password)
    if auth_store.get_user_by_email(email):
        raise AuthError(409, "An account with this email already exists.")
    company = (company_name or "").strip()[:120] or email.split("@", 1)[0].replace(".", " ").title()
    try:
        user = auth_store.create_user(email, hash_password(password))
    except sqlite3.IntegrityError as exc:
        raise AuthError(409, "An account with this email already exists.") from exc
    try:
        org = state.create_org(
            company,
            _unique_slug(company),
            env_prefix=_env_prefix(company),
            plan="free",
        )
        auth_store.add_membership(org["id"], user["id"], "owner")
    except Exception:
        auth_store.delete_user(user["id"])
        raise
    token = auth_store.create_verification(user["id"])
    try:
        email_result = send_verification_email(email, token, company_name=company)
    except Exception as exc:  # noqa: BLE001 - account exists; resend must stay possible
        email_result = AuthEmailResult(False, f"Verification email could not be sent: {exc}")
    return SignupResult(user=user, org=org, verification_token=token, email=email_result)


def login(email: str, password: str) -> SessionResult:
    normalized = auth_store.normalize_email(email)
    user = auth_store.get_user_by_email(normalized)
    if not user or not verify_password(password, user.get("password_hash")):
        raise AuthError(401, "Incorrect email or password.")
    if not user.get("email_verified_at"):
        raise AuthError(403, "Verify your email before signing in.")
    membership = auth_store.primary_org_for_user(user["id"])
    if not membership:
        raise AuthError(403, "This account is not attached to an organization.")
    org = state.get_org(int(membership["org_id"]))
    if not org:
        raise AuthError(403, "The organization for this account no longer exists.")
    token, session = auth_store.create_session(user["id"], org["id"])
    return SessionResult(token=token, user=user, org=org, session=session)


def verify_email(token: str) -> SessionResult:
    user_id = auth_store.consume_verification(token)
    if not user_id:
        raise AuthError(400, "This verification link is invalid or has expired.")
    user = auth_store.mark_email_verified(user_id)
    if not user:
        raise AuthError(400, "This account no longer exists.")
    membership = auth_store.primary_org_for_user(user["id"])
    if not membership:
        raise AuthError(403, "This account is not attached to an organization.")
    org = state.get_org(int(membership["org_id"]))
    if not org:
        raise AuthError(403, "The organization for this account no longer exists.")
    session_token, session = auth_store.create_session(user["id"], org["id"])
    return SessionResult(token=session_token, user=user, org=org, session=session)


def resend_verification(email: str) -> AuthEmailResult:
    """Always returns a generic result to avoid account enumeration."""
    normalized = auth_store.normalize_email(email)
    user = auth_store.get_user_by_email(normalized)
    if not user or user.get("email_verified_at"):
        return AuthEmailResult(True, "If an unverified account exists, a new link has been sent.")
    token = auth_store.create_verification(user["id"])
    try:
        result = send_verification_email(normalized, token)
    except Exception as exc:  # noqa: BLE001
        return AuthEmailResult(False, f"Verification email could not be sent: {exc}", token)
    if result.delivered:
        return AuthEmailResult(True, "If an unverified account exists, a new link has been sent.")
    result.token = token
    return result


def resolve_session(token: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]] | None:
    session = auth_store.get_session(token)
    if not session:
        return None
    user = auth_store.get_user(session["user_id"])
    org = state.get_org(int(session["org_id"]))
    if not user or not org:
        return None
    return user, org, session


def me(user_id: str, org_id: int, session_hash: str | None) -> dict[str, Any]:
    user = auth_store.get_user(user_id)
    org = state.get_org(int(org_id))
    return {
        "authenticated": bool(user and org),
        "user": public_user(user),
        "org": public_org(org),
        "session": "cookie" if session_hash else "basic",
    }
