import asyncio
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import httpx

from app.api import app
import core.sales_store as sales_store
import core.state as state


def test_typed_operational_views_keep_configuration_and_public_links_honest():
    with tempfile.TemporaryDirectory() as directory:
        old_paths = state.DB_PATH, sales_store.DB_PATH
        state.DB_PATH = sales_store.DB_PATH = Path(directory) / "company.db"
        keys = Path(directory) / ".env"
        keys.write_text("HUNTER_API_KEY=private-hunter-key\nSALES_RESEND_DOMAIN=example.test\n")
        try:
            state.init_db()
            sales_store.init_sales_db()

            async def check_routes():
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                    assert (await client.get("/company/ui/session")).status_code == 401
                    assert (await client.get("/company/ui/integrations")).status_code == 401
                    auth = ("founder", "secret")
                    assert (await client.get("/company/ui/session", auth=auth)).json() == {"authenticated": True}
                    integrations = await client.get("/company/ui/integrations", auth=auth)
                    assert integrations.status_code == 200, integrations.text
                    body = integrations.json()
                    assert body["total_groups"] == 6
                    assert body["groups_with_configuration"] == 2
                    assert body["configured_keys"] == 2
                    prospecting = next(group for group in body["groups"] if group["id"] == "prospecting")
                    assert prospecting["configured_keys"] == ["HUNTER_API_KEY"]
                    assert "private-hunter-key" not in integrations.text
                    assert directory not in integrations.text

                    settings = await client.get("/company/ui/settings", auth=auth)
                    assert settings.status_code == 200, settings.text
                    links = {item["id"]: item for item in settings.json()["public_links"]}
                    assert links["app"]["state"] == "local"
                    assert links["forms"]["state"] == "placeholder"
                    assert links["calendar"]["state"] == "local"
                    assert links["forms"]["url"] == "https://forms.example.com/lead"
                    assert "private-query-token" not in settings.text

                    created = await client.post(
                        "/company/marketing/orgs", auth=auth,
                        json={"name": "Acme", "slug": "acme", "domain": "acme.test"},
                    )
                    assert created.status_code == 200, created.text
                    org_id = created.json()["org"]["id"]
                    updated = await client.post(
                        f"/company/marketing/orgs/{org_id}/capabilities", auth=auth,
                        json={"capabilities": {"sales_prospecting": True}},
                    )
                    assert updated.status_code == 200, updated.text
                    selected = await client.post(
                        "/company/marketing/orgs/active", auth=auth, json={"org_id": org_id},
                    )
                    assert selected.status_code == 200, selected.text
                    refreshed = (await client.get("/company/ui/settings", auth=auth)).json()
                    assert refreshed["active_org_id"] == org_id
                    assert refreshed["orgs"][0]["capabilities"]["sales_prospecting"] is True

            with patch.dict(os.environ, {
                "DASHBOARD_USER": "founder", "DASHBOARD_PASSWORD": "secret",
                "SETUP_ENV_FILE": str(keys), "SETUP_G3_ENV_FILE": str(Path(directory) / "missing.env"),
                "COMPANY_PUBLIC_URL": "http://localhost:8787",
                "COMPANY_FORMS_URL": "https://forms.example.com/lead?token=private-query-token",
                "SALES_CALENDAR_BASE_URL": "http://localhost:3000",
                "SALES_CALENDAR_BOOKING_URL": "",
            }):
                asyncio.run(check_routes())
        finally:
            state.DB_PATH, sales_store.DB_PATH = old_paths
