"""Cache policy is stated by the app, not only by the reverse proxy.

Hashed Vite bundles are the only public, year-long cache: their names change
with their bytes. Everything else — tenant data and the SPA shell that points
at the newest bundle — is ``no-store``, so a proxy or CDN added later can only
make things faster, never serve one company's numbers to another.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.api import app


def _cache_control(path: str) -> str:
    response = TestClient(app).get(path)
    return response.headers.get("cache-control", "")


def test_api_and_app_shell_are_not_cacheable():
    assert "no-store" in _cache_control("/health")
    assert "no-store" in _cache_control("/")


def test_hashed_assets_are_immutable_for_a_year():
    # The file need not exist: the header is policy, applied by path. A 404 for
    # a stale bundle must still be marked immutable so browsers stop retrying.
    header = _cache_control("/assets/index-deadbeef.js")
    assert "immutable" in header
    assert "max-age=31536000" in header


def test_browser_hardening_headers_are_sent():
    response = TestClient(app).get("/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    policy = response.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in policy
    # The bundle is the only script on the page; no remote or inline scripts.
    assert "script-src 'self'" in policy
