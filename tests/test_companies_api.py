import asyncio
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import httpx

from app.api import app
import core.sales_store as sales_store
import core.state as state


def test_company_views_use_existing_leads_and_profiles_without_false_name_merges():
    with tempfile.TemporaryDirectory() as directory:
        old_paths = state.DB_PATH, sales_store.DB_PATH
        state.DB_PATH = sales_store.DB_PATH = Path(directory) / "company.db"
        try:
            state.init_db()
            sales_store.init_sales_db()
            candidate, _ = sales_store.upsert_lead({
                "company": "Rift Dynamics", "company_domain": "https://www.rift.test/about",
                "source": "prospeo", "metadata": {"company_candidate": True},
            })
            contact, _ = sales_store.upsert_lead({
                "full_name": "Alex Carter", "email": "alex@rift.test",
                "company": "Rift Dynamics", "company_domain": "rift.test", "source": "website",
            })
            sales_store.upsert_lead({"company": "Shared Name", "source": "manual"})
            sales_store.upsert_lead({"company": "Shared Name", "source": "manual"})
            sales_store.upsert_company_profile(
                "rift.test", provider="companyenrich", status="resolved", company_name="Rift Dynamics",
                summary={"industry": "Software", "employee_range": "50-200", "description": "Workflow automation.",
                         "technologies": ["Python"], "location": {"country": "US"}},
                raw={"private_provider_payload": "do not return"},
            )
            sales_store.upsert_company_profile(
                "orphan.test", provider="pdl", status="resolved", company_name="Orphan Ltd",
                summary={"industry": "Logistics"},
            )

            async def check_routes():
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                    assert (await client.get("/company/sales/companies")).status_code == 401
                    response = await client.get("/company/sales/companies?page_size=2&sort=name", auth=("founder", "secret"))
                    assert response.status_code == 200, response.text
                    body = response.json()
                    assert body["total"] == 4
                    assert len(body["items"]) == 2
                    assert body["metrics"] == {"total": 4, "candidates": 1, "profiled": 2, "with_contacts": 1}
                    second = await client.get("/company/sales/companies?page=2&page_size=2&sort=name", auth=("founder", "secret"))
                    assert len(second.json()["items"]) == 2
                    assert len({item["id"] for item in body["items"] + second.json()["items"]}) == 4

                    found = await client.get("/company/sales/companies?q=Rift&view=with_contacts", auth=("founder", "secret"))
                    assert found.json()["total"] == 1
                    assert found.json()["items"][0]["id"] == "domain:rift.test"
                    assert found.json()["items"][0]["candidate_lead_id"] == candidate["id"]
                    detail = await client.get("/company/sales/companies/domain:rift.test", auth=("founder", "secret"))
                    assert detail.status_code == 200, detail.text
                    value = detail.json()
                    assert value["contact_count"] == 1
                    assert value["contacts"][0]["id"] == contact["id"]
                    assert value["industry"] == "Software"
                    assert value["technologies"] == ["Python"]
                    assert "private_provider_payload" not in detail.text
                    assert (await client.get("/company/sales/companies/domain:missing.test", auth=("founder", "secret"))).status_code == 404
                    assert (await client.get("/company/sales/companies?view=wrong", auth=("founder", "secret"))).status_code == 422

            with patch.dict(os.environ, {"DASHBOARD_USER": "founder", "DASHBOARD_PASSWORD": "secret"}):
                asyncio.run(check_routes())
        finally:
            state.DB_PATH, sales_store.DB_PATH = old_paths


def test_research_action_confirms_new_company_in_authoritative_read():
    with tempfile.TemporaryDirectory() as directory:
        old_paths = state.DB_PATH, sales_store.DB_PATH
        state.DB_PATH = sales_store.DB_PATH = Path(directory) / "company.db"
        try:
            state.init_db()
            sales_store.init_sales_db()

            def research(**_kwargs):
                lead, _ = sales_store.upsert_lead({
                    "company": "New Prospect", "company_domain": "new-prospect.test",
                    "source": "prospeo", "metadata": {"company_candidate": True},
                })
                return {"results": [{"lead": lead, "created": True}], "providers": {"prospeo": 1}, "warnings": [],
                        "requested": {"industry": "Software"}, "mode": "company_first"}

            async def check_routes():
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                    before = await client.get("/company/sales/companies", auth=("founder", "secret"))
                    assert before.json()["total"] == 0
                    denied = await client.post(
                        "/company/sales/research/leads", json={"industry": "Software"}, auth=("founder", "secret"),
                    )
                    assert denied.status_code == 403
                    action = await client.post(
                        "/company/sales/research/leads", json={"industry": "Software"}, auth=("founder", "secret"),
                        headers={"X-Founder-Action-Token": "action-secret"},
                    )
                    assert action.status_code == 200, action.text
                    after = await client.get("/company/sales/companies?view=candidates", auth=("founder", "secret"))
                    assert after.json()["total"] == 1
                    assert after.json()["items"][0]["name"] == "New Prospect"

            with patch.dict(os.environ, {
                "DASHBOARD_USER": "founder", "DASHBOARD_PASSWORD": "secret", "SALES_ACTION_TOKEN": "action-secret",
            }), patch("app.sales_api.research_market_leads", side_effect=research):
                asyncio.run(check_routes())
        finally:
            state.DB_PATH, sales_store.DB_PATH = old_paths
