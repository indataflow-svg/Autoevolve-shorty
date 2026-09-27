"""Isolated persisted records for the workflow browser tests."""

import os
import sys
import tempfile
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.update({
    "DASHBOARD_USER": "founder", "DASHBOARD_PASSWORD": "browser-secret",
    "SALES_ACTION_TOKEN": "browser-action", "SALES_SEND_RECONCILE_ON_STARTUP": "false",
    "RATE_LIMIT_ENABLED": "false",
})

from core import marketing_store, ops_store, sales_store, state  # noqa: E402

db_directory = tempfile.TemporaryDirectory(prefix="workflow-browser-")
pack_directory = tempfile.TemporaryDirectory(prefix="workflow-packs-")
g3_fixture_bin = Path(pack_directory.name) / "g3-fixture"
g3_fixture_bin.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
g3_fixture_bin.chmod(0o700)
os.environ["MARKETING_G3_BIN"] = str(g3_fixture_bin)
state.DB_PATH = sales_store.DB_PATH = marketing_store.DB_PATH = ops_store.DB_PATH = Path(db_directory.name) / "company.db"
state.init_db()
sales_store.init_sales_db()
marketing_store.init_marketing_db()
ops_store.init_db()
ops_store.upsert_incident({
    "id": "incident-browser-1", "service": "hunter", "severity": "warning",
    "status": "open", "trigger": "provider_unavailable",
    "created_at": "2026-09-23T10:00:00+00:00",
})
org = state.create_org("Browser Studio", "browser-studio-workflows", domain="studio.test")
state.set_active_org(org["id"])

lead, _ = sales_store.upsert_lead({"full_name": "Alex Carter", "job_title": "Founder", "company": "Rift Dynamics", "company_domain": "rift.test", "email": "alex@rift.test", "source": "manual"})
sales_store.create_draft(lead["id"], "Helping Rift Dynamics scale operations", "Hi Alex, I would welcome a conversation about your current operations priorities.")

task = state.create_task(org_id=org["id"], agent="growth", task_type="campaign", input_text="Create a campaign")
marketing_store.create_campaign(org_id=org["id"], task_id=task["id"], request="Create a campaign", objective="awareness", buyer="ops_manager", topic="Operations Efficiency Q4", social_platforms=["x"], video_platform="shorts")
marketing_store.create_manual_post(org_id=org["id"], platform="x", post_id="x_browser_workflow", title="Modern Ops with AI", destination_url="https://example.test", tracked_url="https://example.test/?utm_source=x", metadata={"workflow_status": "ready", "generated_caption": "Streamline operations with practical AI."})
marketing_store.create_manual_post(org_id=org["id"], platform="x", post_id="x_browser_sent", title="Published Provider Example", destination_url="https://example.test", tracked_url="https://example.test/?utm_source=x", metadata={
    "workflow_status": "scheduled", "buffer_status": "scheduled", "buffer_account": "default", "buffer_accounts": ["default"],
    "buffer_post_ids": ["buffer-sent-1"], "buffer_result": {"default": {"results": [{"post_id": "buffer-sent-1", "status": "scheduled"}]}},
    "generated_caption": "A saved manual post with a confirmed Buffer ID.",
})
stamp = "2026-09-23T10:00:00+00:00"
with sales_store.connect() as connection:
    connection.execute("UPDATE sales_leads SET created_at = ?, updated_at = ?", (stamp, stamp))
    connection.execute("UPDATE sales_drafts SET created_at = ?, updated_at = ?", (stamp, stamp))
with marketing_store.connect() as connection:
    connection.execute("UPDATE marketing_campaigns SET created_at = ?, updated_at = ?", (stamp, stamp))
    connection.execute("UPDATE marketing_manual_posts SET created_at = ?, updated_at = ?", (stamp, stamp))

import app.marketing_api  # noqa: E402

app.marketing_api.PROJECTS_ROOT = Path(pack_directory.name)
app.marketing_api.spawn_asset_pack = lambda *_args, **_kwargs: None
app.marketing_api.spawn = lambda *_args, **_kwargs: None
app.marketing_api._manual_post_handoff = lambda _post: (Path(pack_directory.name) / "handoff.json", Path(pack_directory.name))


def fixture_g3_run(command, **_kwargs):
    if "accounts" in command:
        return json.dumps({"ok": True, "accounts": [{"name": "default", "organization_id": "buffer-test", "instagram_channel_id": False, "x_channel_id": True}]})
    if "insights" in command:
        post_id = command[-1]
        return json.dumps({"ok": True, "provider": "buffer", "post": {
            "id": post_id, "status": "sent" if post_id == "buffer-sent-1" else "scheduled",
            "dueAt": "2026-09-25T10:00:00Z", "externalLink": "https://example.test/buffer-post",
            "metrics": [{"type": "reactions", "name": "Reactions", "value": 12, "unit": "count"}] if post_id == "buffer-sent-1" else None,
            "metricsUpdatedAt": "2026-09-24T09:00:00Z" if post_id == "buffer-sent-1" else None,
        }})
    if "schedule" in command:
        return json.dumps({"ok": True, "provider": "buffer", "scheduled": True, "results": [{"platform": "x", "status": "scheduled", "post_id": "buffer-scheduled-2"}]})
    raise RuntimeError("unexpected G3 fixture command")


app.marketing_api._run = fixture_g3_run

from app.api import app  # noqa: E402
import uvicorn  # noqa: E402

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8789, log_level="warning")
