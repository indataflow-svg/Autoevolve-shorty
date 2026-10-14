"""OAuth lifecycle for catalog providers: authorize, callback, refresh, revoke.

Implemented to completion; only the external credentials are missing. A
provider with its client id and secret configured moves from catalog-only to
connectable with zero code changes: the catalog, the authorize URL, the
callback, and the refresh path all key off the same registry below.

Secrets never touch logs, errors, or API responses. Tokens rest encrypted
(Fernet, key from OAUTH_TOKEN_KEY) in integration_secrets; only the
credential reference and health state live on the connection row.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
import urllib.parse
import urllib.request
from typing import Any


class OAuthError(ValueError):
    """Provider refused, state invalid, or configuration missing."""


class OAuthNotConfigured(OAuthError):
    """The external app approval (client id/secret) is not in the environment."""


PROVIDERS: dict[str, dict[str, Any]] = {
    "hubspot": {
        "label": "HubSpot CRM",
        "auth_url": "https://app.hubspot.com/oauth/authorize",
        "token_url": "https://api.hubapi.com/oauth/v1/token",
        "scopes": ["crm.objects.contacts.read", "crm.objects.contacts.write",
                   "crm.objects.companies.read"],
        "docs": "Create a private-app... use a public app: Developers > Manage apps > Create app; "
                "set the redirect URL to <public-base>/company/commercial/integrations/hubspot/callback",
    },
    "salesforce": {
        "label": "Salesforce",
        "auth_url": "https://login.salesforce.com/services/oauth2/authorize",
        "token_url": "https://login.salesforce.com/services/oauth2/token",
        "scopes": ["api", "refresh_token", "offline_access"],
        "docs": "Create a Connected App (Setup > App Manager > New Connected App) with "
                "oauth scope api + refresh_token; set the callback URL to "
                "<public-base>/company/commercial/integrations/salesforce/callback",
    },
    "google_ads": {
        "label": "Google Ads",
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scopes": ["https://www.googleapis.com/auth/adwords"],
        "docs": "Google Cloud console > Credentials > OAuth client ID (Web); add "
                "<public-base>/company/commercial/integrations/google_ads/callback "
                "as an authorized redirect URI",
    },
    "google_analytics": {
        "label": "Google Analytics",
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scopes": ["https://www.googleapis.com/auth/analytics.readonly"],
        "docs": "Same OAuth client as Google Ads; add the analytics callback URL likewise",
    },
    "meta_ads": {
        "label": "Meta Ads",
        "auth_url": "https://www.facebook.com/v18.0/dialog/oauth",
        "token_url": "https://graph.facebook.com/v18.0/oauth/access_token",
        "scopes": ["ads_read", "ads_management"],
        "docs": "Meta Developers > Create app (Business) > add Marketing API; valid OAuth "
                "redirect URI: <public-base>/company/commercial/integrations/meta_ads/callback",
    },
    "whatsapp": {
        "label": "WhatsApp Business",
        "auth_url": "https://www.facebook.com/v18.0/dialog/oauth",
        "token_url": "https://graph.facebook.com/v18.0/oauth/access_token",
        "scopes": ["whatsapp_business_messaging", "whatsapp_business_management"],
        "docs": "Same Meta app with the WhatsApp product added and a phone number "
                "connected; same callback pattern under /whatsapp/callback",
    },
}

STATE_TTL_SECONDS = 600


def _client_id(provider: str) -> str:
    return os.getenv(f"{provider.upper()}_CLIENT_ID", "").strip()


def _client_secret(provider: str) -> str:
    return os.getenv(f"{provider.upper()}_CLIENT_SECRET", "").strip()


def is_configured(provider: str) -> bool:
    """External app approval exists when both halves are present. Nothing else counts."""
    return provider in PROVIDERS and bool(_client_id(provider)) and bool(_client_secret(provider))


def missing_config(provider: str) -> list[str]:
    return [v for v in (f"{provider.upper()}_CLIENT_ID", f"{provider.upper()}_CLIENT_SECRET")
            if not os.getenv(v, "").strip()]


def _signing_key() -> bytes:
    secret = os.getenv("SALES_ACTION_TOKEN", "")
    if not secret:
        raise OAuthNotConfigured("SALES_ACTION_TOKEN is not configured")
    return secret.encode()


def _public_base() -> str:
    return (os.getenv("COMPANY_PUBLIC_URL", "") or "http://localhost:8787").rstrip("/")


def _callback_url(provider: str) -> str:
    return f"{_public_base()}/company/commercial/integrations/{provider}/callback"


def build_authorize_url(provider: str, org_id: int = 0) -> str:
    """Start the provider's official authorization flow. Founder-gated upstream."""
    if provider not in PROVIDERS:
        raise OAuthError(f"unknown provider {provider!r}")
    if not is_configured(provider):
        raise OAuthNotConfigured(
            f"{provider} credentials are not configured: set {', '.join(missing_config(provider))}")
    nonce = secrets.token_urlsafe(16)
    expiry = str(int(time.time()) + STATE_TTL_SECONDS)
    payload = f"{provider}.{org_id}.{nonce}.{expiry}"
    signature = hmac.new(_signing_key(), payload.encode(), hashlib.sha256).hexdigest()
    params = {
        "client_id": _client_id(provider),
        "redirect_uri": _callback_url(provider),
        "response_type": "code",
        "scope": " ".join(PROVIDERS[provider]["scopes"]),
        "state": f"{payload}.{signature}",
    }
    return f"{PROVIDERS[provider]['auth_url']}?{urllib.parse.urlencode(params)}"


def verify_state(provider: str, raw_state: str, org_id: int = 0) -> None:
    """The callback's only authentication. Rejects tampering, expiry, and mismatch."""
    try:
        prov, org, nonce, expiry, signature = raw_state.split(".")
    except ValueError:
        raise OAuthError("authorization state is malformed")
    if prov != provider or org != str(org_id):
        raise OAuthError("authorization state does not match this provider")
    try:
        if int(expiry) < int(time.time()):
            raise OAuthError("authorization expired; start over from Connect")
    except ValueError:
        raise OAuthError("authorization state is malformed")
    expected = hmac.new(
        _signing_key(), f"{prov}.{org}.{nonce}.{expiry}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise OAuthError("authorization signature is invalid")


def _post_form(url: str, fields: dict[str, str]) -> dict[str, Any]:
    body = urllib.parse.urlencode(fields).encode()
    request = urllib.request.Request(url, data=body, method="POST",
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        raise OAuthError(f"provider refused the token request ({exc.code})")
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise OAuthError(f"token request failed: {type(exc).__name__}")
    if "error" in payload:
        raise OAuthError(f"provider refused: {payload.get('error_description') or payload['error']}")
    if "access_token" not in payload:
        raise OAuthError("provider response carried no access token")
    return payload


def _fernet():
    from cryptography.fernet import Fernet

    raw = os.getenv("OAUTH_TOKEN_KEY", "").strip()
    if not raw:
        raise OAuthNotConfigured("OAUTH_TOKEN_KEY is not configured; generate one and store it server-side")
    try:
        return Fernet(raw.encode())
    except ValueError:
        raise OAuthNotConfigured("OAUTH_TOKEN_KEY is not a valid Fernet key")


def store_tokens(provider: str, tokens: dict[str, Any], org_id: int = 0) -> None:
    """Encrypt and persist. Plaintext tokens never reach the database."""
    from core import commercial_store
    from core.state import now_iso

    blob = _fernet().encrypt(json.dumps({
        "access_token": tokens.get("access_token"),
        "refresh_token": tokens.get("refresh_token"),
        "token_type": tokens.get("token_type", "Bearer"),
        "scope": tokens.get("scope", ""),
    }).encode()).decode()
    expires_at = None
    try:
        lifetime = int(tokens.get("expires_in") or 0)
        if lifetime > 0:
            expires_at = int(time.time()) + lifetime
    except (TypeError, ValueError):
        expires_at = None
    timestamp = now_iso()
    with commercial_store.connect() as db:
        db.execute(
            "INSERT INTO integration_secrets (org_id, provider, ciphertext, scopes,"
            " expires_at, created_at, updated_at) VALUES (?,?,?,?,?,?,?)"
            " ON CONFLICT(org_id, provider) DO UPDATE SET ciphertext=excluded.ciphertext,"
            " scopes=excluded.scopes, expires_at=excluded.expires_at, updated_at=excluded.updated_at",
            (org_id, provider, blob, " ".join(PROVIDERS[provider]["scopes"]),
             expires_at, timestamp, timestamp),
        )


def read_tokens(provider: str, org_id: int = 0) -> dict[str, Any] | None:
    """Decrypt for server-side use only. Never returned by any API."""
    from core import commercial_store

    with commercial_store.connect() as db:
        row = db.execute(
            "SELECT ciphertext FROM integration_secrets WHERE org_id=? AND provider=?",
            (org_id, provider)).fetchone()
    if not row:
        return None
    try:
        return json.loads(_fernet().decrypt(row["ciphertext"].encode()).decode())
    except Exception as exc:
        raise OAuthError(f"stored credentials cannot be decrypted: {type(exc).__name__}")


def delete_tokens(provider: str, org_id: int = 0) -> None:
    from core import commercial_store

    with commercial_store.connect() as db:
        db.execute("DELETE FROM integration_secrets WHERE org_id=? AND provider=?",
                   (org_id, provider))


def exchange_code(provider: str, code: str, org_id: int = 0) -> dict[str, Any]:
    """Trade one single-use authorization code for tokens, then persist them."""
    if provider not in PROVIDERS:
        raise OAuthError(f"unknown provider {provider!r}")
    tokens = _post_form(PROVIDERS[provider]["token_url"], {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": _callback_url(provider),
        "client_id": _client_id(provider),
        "client_secret": _client_secret(provider),
    })
    store_tokens(provider, tokens, org_id)
    return {"provider": provider, "scope": tokens.get("scope", ""),
            "expires_in": tokens.get("expires_in")}


def refresh_tokens(provider: str, org_id: int = 0) -> dict[str, Any]:
    """Rotate an expiring access token. Failure surfaces as action-required, never silent."""
    stored = read_tokens(provider, org_id)
    if not stored or not stored.get("refresh_token"):
        raise OAuthError("no refresh token stored; reconnect the provider")
    tokens = _post_form(PROVIDERS[provider]["token_url"], {
        "grant_type": "refresh_token",
        "refresh_token": stored["refresh_token"],
        "client_id": _client_id(provider),
        "client_secret": _client_secret(provider),
    })
    if not tokens.get("refresh_token"):
        tokens["refresh_token"] = stored["refresh_token"]
    store_tokens(provider, tokens, org_id)
    return {"provider": provider, "refreshed": True}


def validate_connection(provider: str, org_id: int = 0) -> dict[str, Any]:
    """Health check used by sync: refresh when expiring, report honestly."""
    stored = read_tokens(provider, org_id)
    if not stored:
        return {"healthy": False, "reason": "no stored credentials; connect the provider"}
    if stored.get("refresh_token"):
        try:
            refresh_tokens(provider, org_id)
            return {"healthy": True, "refreshed": True}
        except OAuthError as exc:
            return {"healthy": False, "reason": str(exc)}
    if stored.get("access_token"):
        return {"healthy": True, "refreshed": False,
                "note": "provider issued no refresh token; reconnect when calls fail"}
    return {"healthy": False, "reason": "stored credentials are empty; reconnect the provider"}
