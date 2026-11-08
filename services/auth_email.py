"""Transactional email for website authentication.

Resend is used when configured. Without a key (local development, tests) the
verification link is written to the server log and returned to the caller only
when ``AUTH_EXPOSE_DEV_TOKEN=true``.
"""
from __future__ import annotations

import html
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from email.utils import parseaddr
from urllib.parse import quote

RESEND_SEND_URL = "https://api.resend.com/emails"


@dataclass
class AuthEmailResult:
    delivered: bool
    detail: str
    token: str | None = None


def verify_url(token: str) -> str:
    base = os.getenv("AUTH_VERIFY_BASE_URL", "http://localhost:4181/verify").strip()
    if not base:
        base = "http://localhost:4181/verify"
    # The token stays in the fragment so Cloudflare, nginx, application logs,
    # and the Referer header never receive it.
    base = base.split("#", 1)[0]
    return f"{base}#token={quote(token, safe='')}"


def _sender() -> str:
    explicit = (os.getenv("AUTH_FROM_EMAIL") or os.getenv("SALES_FROM_EMAIL") or "").strip()
    domain = (os.getenv("AUTH_RESEND_DOMAIN") or os.getenv("SALES_RESEND_DOMAIN") or "").strip()
    display_name = (os.getenv("AUTH_FROM_NAME") or os.getenv("COMPANY_NAME") or "AutoEvolve").strip() or "AutoEvolve"
    if explicit:
        local = parseaddr(explicit)[1].split("@", 1)[0] or "noreply"
        if domain:
            return f"{display_name} <{local}@{domain}>"
        return explicit
    if domain:
        return f"{display_name} <noreply@{domain}>"
    return ""


def _api_key() -> str:
    return (os.getenv("AUTH_RESEND_API_KEY") or os.getenv("SALES_RESEND_API_KEY") or "").strip()


def send_verification_email(email: str, token: str, *, company_name: str = "") -> AuthEmailResult:
    link = verify_url(token)
    sender = _sender()
    api_key = _api_key()
    if not api_key or not sender:
        print(f"[auth] verification link for {email}: {link}")
        return AuthEmailResult(False, "Email delivery is not configured; the verification link was logged.")
    subject = "Verify your AutoEvolve email"
    greeting = f"Welcome to AutoEvolve{f', {company_name}' if company_name else ''}."
    text = (
        f"{greeting}\n\nVerify your email to start your daily loop:\n{link}\n\n"
        "This link expires in 24 hours. If you did not create an account, ignore this email."
    )
    safe_link = html.escape(link)
    safe_greeting = html.escape(greeting)
    body = {
        "from": sender,
        "to": [email],
        "subject": subject,
        "text": text,
        "html": (
            "<div style=\"font-family:system-ui,sans-serif;max-width:520px;margin:0 auto;padding:32px\">"
            f"<p>{safe_greeting}</p><p>Verify your email to start your daily loop.</p>"
            f"<p><a href=\"{safe_link}\" style=\"background:#111;color:#fff;padding:12px 20px;"
            "border-radius:8px;text-decoration:none;display:inline-block\">Verify email</a></p>"
            "<p style=\"color:#666;font-size:13px\">This link expires in 24 hours.</p></div>"
        ),
    }
    request = urllib.request.Request(
        RESEND_SEND_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "autoevolve-auth/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"Resend rejected the verification email (HTTP {exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Resend is unreachable: {exc}") from exc
    return AuthEmailResult(True, "Verification email sent.")


def dev_token_visible() -> bool:
    return os.getenv("AUTH_EXPOSE_DEV_TOKEN", "").strip().lower() in {"1", "true", "yes"}
