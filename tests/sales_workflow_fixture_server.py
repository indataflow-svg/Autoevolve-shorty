"""Isolated persisted sales records for Replies and Meetings browser checks."""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.update({
    "DASHBOARD_USER": "founder", "DASHBOARD_PASSWORD": "browser-secret",
    "SALES_ACTION_TOKEN": "browser-action", "SALES_SEND_RECONCILE_ON_STARTUP": "false",
    "RATE_LIMIT_ENABLED": "false",
})

from core import sales_store, state  # noqa: E402

database_directory = tempfile.TemporaryDirectory(prefix="sales-workflow-browser-")
state.DB_PATH = sales_store.DB_PATH = Path(database_directory.name) / "company.db"
state.init_db()
sales_store.init_sales_db()

people = [
    ("Alex Carter", "Rift Dynamics", "Founder", "alex@rift.test"),
    ("Priya Shah", "Luma Logistics", "Head of Operations", "priya@luma.test"),
    ("Daniel Kim", "Kairo Tech", "CTO", "daniel@kairo.test"),
    ("Elena Ruiz", "Meridian Labs", "Head of Growth", "elena@meridian.test"),
    ("James Okoro", "Fieldworks", "Founder", "james@fieldworks.test"),
    ("Sophia Martinez", "TerraBuild", "VP Engineering", "sophia@terra.test"),
]
for index, (name, company, role, email) in enumerate(people):
    lead, _ = sales_store.upsert_lead({"full_name": name, "company": company, "job_title": role, "email": email, "source": "manual"})
    sales_store.mark_replied(lead["id"], f"Re: Operations at {company}",
                             "Could you share the next step for our operations team?" if index == 0 else f"Please send more information about {company}.",
                             f"<browser-reply-{index}@test>")
    if index == 5:
        sales_store.add_interaction(lead["id"], "outbound", "email", "outreach", "Follow-up", "Thanks for your response.")
    if index < 5:
        sales_store.mark_meeting_scheduled(
            lead["id"], scheduled_for=f"2026-09-{26 + index:02}T10:00:00Z",
            note="Discuss the saved inbound request." if index == 0 else f"Review {company} priorities.",
        )

with sales_store.connect() as connection:
    connection.execute("UPDATE sales_interactions SET created_at = printf('2026-09-24T10:%02d:00Z', id)")
    connection.execute("UPDATE sales_leads SET metadata_json = json_set(metadata_json, '$.meeting.updated_at', '2026-09-24T10:00:00Z') WHERE json_extract(metadata_json, '$.meeting.status') = 'scheduled'")


async def fixture_draft(lead):
    from agents.sales import OutreachDraft
    return OutreachDraft(
        subject=f"Follow-up for {lead.get('company') or 'your team'}",
        body="Hi, I would be glad to share more details and discuss the next step with your operations team.",
        rationale="Browser fixture provider substitute.", call_to_action="reply",
    )


import agents.sales  # noqa: E402
agents.sales.draft_outreach = fixture_draft

from app.api import app  # noqa: E402
import uvicorn  # noqa: E402

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8790, log_level="warning")
