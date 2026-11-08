import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import httpx

from app.api import app
import core.sales_store as sales_store
import core.state as state
from core.auth_security import hash_password, verify_password


def test_password_hash_round_trip():
    encoded = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", encoded)
    assert not verify_password("wrong password", encoded)
    assert encoded.startswith("scrypt$")


def test_verify_link_uses_fragment_token():
    from services.auth_email import verify_url

    with patch.dict(os.environ, {"AUTH_VERIFY_BASE_URL": "https://example.com/verify"}):
        assert verify_url("abc 123") == "https://example.com/verify#token=abc%20123"


def test_signup_verify_login_and_org_scope():
    with tempfile.TemporaryDirectory() as directory:
        old_paths = state.DB_PATH, sales_store.DB_PATH
        state.DB_PATH = sales_store.DB_PATH = Path(directory) / "company.db"
        try:
            state.init_db()
            sales_store.init_sales_db()
            env = {
                "RATE_LIMIT_ENABLED": "false",
                "AUTH_EXPOSE_DEV_TOKEN": "true",
                "AUTH_RESEND_API_KEY": "",
                "SALES_RESEND_API_KEY": "",
                "APP_ENCRYPTION_KEY": "auth-test-key",
                "AUTH_ALLOWED_ORIGINS": "http://testserver",
                "AUTH_COOKIE_SECURE": "false",
                "AUTH_COOKIE_DOMAIN": "",
                "AUTH_COOKIE_NAME": "autoevolve_session",
                "PUBLISHER_WEBHOOK_URL": "",
                "PUBLISHER_WEBHOOK_SECRET": "",
            }
            with patch.dict(os.environ, env, clear=False):
                async def run():
                    transport = httpx.ASGITransport(app=app)
                    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as first:
                        signup = await first.post(
                            "/api/auth/signup",
                            json={
                                "email": "one@example.com",
                                "password": "correct horse battery",
                                "company_name": "One Co",
                            },
                        )
                        assert signup.status_code == 200, signup.text
                        signup_body = signup.json()
                        assert signup_body["verification_required"] is True
                        assert signup_body["org"]["plan"] == "free"
                        token = signup_body["dev_token"]

                        unverified = await first.post(
                            "/api/auth/login",
                            json={"email": "one@example.com", "password": "correct horse battery"},
                        )
                        assert unverified.status_code == 403

                        verified = await first.post("/api/auth/verify", json={"token": token})
                        assert verified.status_code == 200, verified.text
                        first_org = verified.json()["org"]["id"]
                        me = await first.get("/api/auth/me")
                        assert me.status_code == 200, me.text
                        assert me.json()["org"]["id"] == first_org
                        assert me.json()["user"]["email_verified"] is True
                        quot = await first.get("/company/ui/quotas")
                        assert quot.status_code == 200, quot.text
                        assert quot.json()["plan"] == "free"
                        assert quot.json()["quotas"]["plans"]["limit"] == 1

                        saved = await first.put(
                            "/company/ui/publishers/webhook",
                            json={
                                "url": "https://hooks.one.example.test/autoevolve",
                                "secret": "one-secret-at-least-16",
                                "account": "one-hook",
                                "label": "One hook",
                                "platforms": "instagram,x",
                            },
                        )
                        assert saved.status_code == 200, saved.text
                        assert saved.json()["webhook"]["secret_set"] is True
                        catalog = await first.get("/company/marketing/publishers")
                        assert catalog.status_code == 200, catalog.text
                        assert [item["name"] for item in catalog.json()["publishers"]] == ["webhook"]
                        accounts = await first.get("/company/marketing/publisher-accounts?publisher=webhook")
                        assert accounts.status_code == 200, accounts.text
                        assert accounts.json()["accounts"][0]["name"] == "one-hook"

                        login = await first.post(
                            "/api/auth/login",
                            json={"email": "one@example.com", "password": "correct horse battery"},
                        )
                        assert login.status_code == 200, login.text
                        assert login.json()["org"]["id"] == first_org

                        second = httpx.AsyncClient(transport=transport, base_url="http://testserver")
                        try:
                            signup_two = await second.post(
                                "/api/auth/signup",
                                json={
                                    "email": "two@example.com",
                                    "password": "another good password",
                                    "company_name": "Two Co",
                                },
                            )
                            assert signup_two.status_code == 200, signup_two.text
                            verified_two = await second.post(
                                "/api/auth/verify", json={"token": signup_two.json()["dev_token"]}
                            )
                            assert verified_two.status_code == 200, verified_two.text
                            second_org = verified_two.json()["org"]["id"]
                            assert second_org != first_org
                            second_me = await second.get("/api/auth/me")
                            assert second_me.json()["org"]["id"] == second_org
                        finally:
                            await second.aclose()

                        settings = await first.get("/company/ui/settings")
                        assert settings.status_code == 200, settings.text
                        assert [org["id"] for org in settings.json()["orgs"]] == [first_org]
                        marketing_orgs = await first.get("/company/marketing/orgs")
                        assert marketing_orgs.status_code == 200, marketing_orgs.text
                        assert [org["id"] for org in marketing_orgs.json()["orgs"]] == [first_org]
                        denied_switch = await first.post(
                            "/company/marketing/orgs/active", json={"org_id": second_org}
                        )
                        assert denied_switch.status_code == 404
                        denied_create = await first.post(
                            "/company/marketing/orgs",
                            json={"name": "Third Co", "slug": "third-co", "domain": "", "capabilities": {}},
                        )
                        assert denied_create.status_code == 403
                        denied_buffer = await first.get(
                            "/company/marketing/publisher-accounts?publisher=buffer"
                        )
                        assert denied_buffer.status_code == 403
                        bad_origin = await first.post(
                            "/company/ui/limits",
                            headers={"Origin": "https://evil.example"},
                            json={"max_actions": 1},
                        )
                        assert bad_origin.status_code == 403
                        for operator_only in (
                            "/company/setup/providers",
                            "/company/incidents",
                            "/company/commercial/forms",
                            "/company/ui/integrations",
                        ):
                            denied = await first.get(operator_only)
                            assert denied.status_code == 403, (operator_only, denied.text)

                        logout = await first.post("/api/auth/logout")
                        assert logout.status_code == 200
                        assert (await first.get("/api/auth/me")).status_code == 401
                        # A stale cookie must not delete the fresh cookie set by login.
                        first.cookies.set("autoevolve_session", "stale-invalid-token", domain="testserver.local")
                        relogin = await first.post(
                            "/api/auth/login",
                            json={"email": "one@example.com", "password": "correct horse battery"},
                        )
                        assert relogin.status_code == 200, relogin.text
                        assert (await first.get("/api/auth/me")).status_code == 200

                import asyncio

                asyncio.run(run())
        finally:
            state.DB_PATH, sales_store.DB_PATH = old_paths
