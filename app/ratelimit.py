"""In-app sliding-window rate limits for public intake, provider webhooks
and failed dashboard sign-ins.

These are a coarse backstop for a self-hosted single-node deployment, not a
replacement for the reverse-proxy limits in docs/production-checklist.md.
State is per process and in memory: that is enough while there is one API
process (see the V2 plan non-goals - no Redis).
"""
from __future__ import annotations

import os
import time

from fastapi import HTTPException, Request

WINDOW_SECONDS = 60

# Intake and webhook POSTs under /integrations that are fired by external
# providers or form tools rather than a human clicking the dashboard.
WEBHOOK_PATHS = (
    "/integrations/email/sales",
    "/integrations/resend/sales",
    "/integrations/leads/tally",
)

_hits: dict[str, list[float]] = {}

_MAX_KEYS = 5000


def reset() -> None:
    """Drop all recorded hits (tests)."""
    _hits.clear()


def enabled() -> bool:
    return os.getenv("RATE_LIMIT_ENABLED", "true").strip().lower() not in {"0", "false", "no"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    try:
        value = int(raw) if raw else default
    except ValueError:
        value = default
    return max(1, value)


def client_ip(request: Request) -> str:
    if os.getenv("RATE_LIMIT_TRUST_PROXY", "false").strip().lower() in {"1", "true", "yes"}:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _window(key: str, now: float) -> list[float]:
    hits = [t for t in _hits.get(key, []) if now - t < WINDOW_SECONDS]
    if hits:
        _hits[key] = hits
    elif key in _hits:
        del _hits[key]
    return hits


def _enforce(kind: str, request: Request, limit: int) -> None:
    if not enabled():
        return
    key = f"{kind}:{client_ip(request)}"
    now = time.monotonic()
    if len(_hits) > _MAX_KEYS:
        for stale in [k for k, v in list(_hits.items()) if not v or now - max(v) >= WINDOW_SECONDS]:
            _hits.pop(stale, None)
    hits = _window(key, now)
    if len(hits) >= limit:
        retry_after = max(1, int(WINDOW_SECONDS - (now - hits[0])) + 1)
        raise HTTPException(
            429,
            f"rate limit exceeded, retry in {retry_after}s",
            headers={"Retry-After": str(retry_after)},
        )
    hits.append(now)
    _hits[key] = hits


def rate_limit_intake(request: Request) -> None:
    """Router dependency for /integrations routes: webhooks and form intake
    get their own budgets so a provider retry storm cannot starve the form."""
    if not enabled():
        return
    if request.url.path in WEBHOOK_PATHS:
        _enforce("webhook", request, _env_int("RATE_LIMIT_WEBHOOK_PER_MINUTE", 120))
    else:
        _enforce("intake", request, _env_int("RATE_LIMIT_INTAKE_PER_MINUTE", 30))


def check_auth_failure(request: Request) -> None:
    """Count failed dashboard sign-ins per IP (separate bucket, counts only
    failures so legitimate traffic can never lock itself out)."""
    if not enabled():
        return
    limit = _env_int("RATE_LIMIT_AUTH_FAILURES_PER_MINUTE", 10)
    key = f"auth_fail:{client_ip(request)}"
    now = time.monotonic()
    hits = _window(key, now)
    hits.append(now)
    _hits[key] = hits
    if len(hits) > limit:
        retry_after = max(1, int(WINDOW_SECONDS - (now - hits[0])) + 1)
        raise HTTPException(
            429,
            "too many failed sign-in attempts",
            headers={"Retry-After": str(retry_after)},
        )
