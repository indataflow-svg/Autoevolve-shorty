"""Read projections reuse existing stores without inventing workflow state."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api import app
import core.marketing_store as marketing_store
import core.sales_store as sales_store
import core.state as state


def test_workflow_read_views_keep_draft_campaign_and_post_semantics_separate():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        old_paths = state.DB_PATH, sales_store.DB_PATH, marketing_store.DB_PATH
        state.DB_PATH = sales_store.DB_PATH = marketing_store.DB_PATH = root / "company.db"
        try:
            state.init_db()
            sales_store.init_sales_db()
            marketing_store.init_marketing_db()
            org = state.create_org("Example Brand", "example-brand-workflow-test")
            state.set_active_org(org["id"])
            lead, _ = sales_store.upsert_lead({"full_name": "Avery Doe", "email": "avery@example.test", "company": "Example Prospect", "source": "manual"})
            draft = sales_store.create_draft(lead["id"], "A useful subject", "A complete message body.")
            task = state.create_task(org_id=org["id"], agent="growth", task_type="campaign", input_text="Create campaign")
            campaign = marketing_store.create_campaign(org_id=org["id"], task_id=task["id"], request="Create campaign", objective="awareness", buyer="ops_manager", topic="Workflow clarity", social_platforms=["x"], video_platform="shorts")
            post = marketing_store.create_manual_post(org_id=org["id"], platform="x", post_id="x_workflow_test", title="A manual post", destination_url="https://example.test", tracked_url="https://example.test/?utm_source=x", metadata={"workflow_status": "buffer_draft", "buffer_status": "drafted"})
            with patch.dict(os.environ, {"DASHBOARD_USER": "founder", "DASHBOARD_PASSWORD": "test-secret"}), patch("app.marketing_api.PROJECTS_ROOT", root):
                client = TestClient(app)
                assert client.get("/company/ui/outreach").status_code == 401
                auth = ("founder", "test-secret")
                outreach = client.get("/company/ui/outreach?q=Example%20Prospect&sort=company", auth=auth)
                assert outreach.status_code == 200, outreach.text
                assert outreach.json()["total"] == 1
                assert outreach.json()["items"][0]["status"] == "draft"
                assert outreach.json()["items"][0]["id"] == draft["id"]
                assert client.get("/company/ui/outreach/missing", auth=auth).status_code == 404
                assert client.get("/company/ui/outreach?page_size=0", auth=auth).status_code == 422
                campaigns = client.get("/company/ui/campaigns?org_id=" + str(org["id"]), auth=auth)
                assert campaigns.status_code == 200, campaigns.text
                assert campaigns.json()["items"][0]["status"] == "queued"
                assert campaigns.json()["items"][0]["g3_status"] == "not_requested"
                assert client.get(f"/company/ui/campaigns/{campaign['id']}", auth=auth).status_code == 200
                assert client.get("/company/ui/campaigns/missing", auth=auth).status_code == 404
                assert client.get("/company/ui/campaigns?sort=Recent", auth=auth).status_code == 422
                content = client.get("/company/ui/content", auth=auth)
                assert content.status_code == 200, content.text
                assert content.json()["items"][0]["id"] == post["id"]
                assert content.json()["items"][0]["stage"] == "buffer_draft"
                assert content.json()["items"][0]["buffer_status"] == "drafted"
                home = client.get("/company/ui/home", auth=auth)
                assert home.status_code == 200, home.text
                assert home.json()["outreach_drafts_total"] == 1
                assert home.json()["campaigns_total"] == 1
                assert home.json()["manual_posts_total"] == 1
        finally:
            state.DB_PATH, sales_store.DB_PATH, marketing_store.DB_PATH = old_paths


def test_empty_workflow_views_return_empty_records_not_failure():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        old_paths = state.DB_PATH, sales_store.DB_PATH, marketing_store.DB_PATH
        state.DB_PATH = sales_store.DB_PATH = marketing_store.DB_PATH = root / "empty.db"
        try:
            state.init_db()
            sales_store.init_sales_db()
            marketing_store.init_marketing_db()
            with patch.dict(os.environ, {"DASHBOARD_USER": "founder", "DASHBOARD_PASSWORD": "test-secret"}), patch("app.marketing_api.PROJECTS_ROOT", root):
                client = TestClient(app)
                auth = ("founder", "test-secret")
                for path in ("/company/ui/outreach", "/company/ui/campaigns", "/company/ui/content"):
                    response = client.get(path, auth=auth)
                    assert response.status_code == 200, response.text
                    assert response.json()["items"] == []
                home = client.get("/company/ui/home", auth=auth)
                assert home.status_code == 200, home.text
                assert home.json()["contacts_total"] == 0
                assert home.json()["active_org_name"] is None
        finally:
            state.DB_PATH, sales_store.DB_PATH, marketing_store.DB_PATH = old_paths
