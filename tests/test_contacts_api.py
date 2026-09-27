import asyncio
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import httpx

from app.api import app
import core.sales_store as sales_store
import core.state as state


def test_contacts_are_paginated_filtered_and_typed():
    with tempfile.TemporaryDirectory() as directory:
        old_paths = state.DB_PATH, sales_store.DB_PATH
        state.DB_PATH = sales_store.DB_PATH = Path(directory) / "company.db"
        try:
            state.init_db()
            sales_store.init_sales_db()
            for number in range(23):
                sales_store.upsert_lead({
                    "full_name": f"Contact {number:02}",
                    "email": f"contact{number}@example.com",
                    "company": "Acme",
                    "source": "manual",
                    "verification_status": "valid" if number < 3 else None,
                })
            async def check_routes():
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                    denied = await client.get("/company/sales/contacts")
                    assert denied.status_code == 401
                    assert denied.headers["www-authenticate"] == "Basic"

                    ajax_denied = await client.get(
                        "/company/sales/contacts",
                        auth=("founder", "wrong"),
                        headers={"X-Requested-With": "XMLHttpRequest"},
                    )
                    assert ajax_denied.status_code == 401
                    assert "www-authenticate" not in ajax_denied.headers

                    response = await client.get("/company/sales/contacts?page=3&page_size=10&sort=name", auth=("founder", "secret"))
                    assert response.status_code == 200, response.text
                    body = response.json()
                    assert body["total"] == 23
                    assert len(body["items"]) == 3
                    assert body["items"][0]["full_name"] == "Contact 20"
                    assert {key: body["metrics"][key] for key in ("total", "ready", "verified", "suppressed")} == {"total": 23, "ready": 23, "verified": 3, "suppressed": 0}
                    assert sum(body["metrics"]["by_stage"].values()) == 23
                    assert body["items"][0]["last_touch_at"] is None

                    search = await client.get("/company/sales/contacts?q=Contact%2022", auth=("founder", "secret"))
                    assert search.json()["total"] == 1
                    contact_id = search.json()["items"][0]["id"]
                    detail = await client.get(f"/company/sales/contacts/{contact_id}", auth=("founder", "secret"))
                    assert detail.status_code == 200, detail.text
                    assert detail.json()["contact_profile"]["email_ready"] is True
                    assert detail.json()["drafts"] == []

                    invalid = await client.get("/company/sales/contacts?sort=unsupported", auth=("founder", "secret"))
                    assert invalid.status_code == 422

            with patch.dict(os.environ, {"DASHBOARD_USER": "founder", "DASHBOARD_PASSWORD": "secret"}):
                asyncio.run(check_routes())
        finally:
            state.DB_PATH, sales_store.DB_PATH = old_paths
