"""Run the real FastAPI app against an isolated SQLite fixture for browser tests."""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

os.environ["DASHBOARD_USER"] = "founder"
os.environ["DASHBOARD_PASSWORD"] = "browser-secret"
os.environ["SALES_ACTION_TOKEN"] = "browser-action"
os.environ["SALES_SEND_RECONCILE_ON_STARTUP"] = "false"
os.environ["RATE_LIMIT_ENABLED"] = "false"

# Provider-key actions in browser tests must never write the real repository env files.
setup_directory = tempfile.TemporaryDirectory(prefix="autoevolve-setup-browser-")
setup_env = Path(setup_directory.name) / ".env"
setup_g3_env = Path(setup_directory.name) / "g3.env"
setup_env.write_text("PEXELS_API_KEY=existing-test-value\n", encoding="utf-8")
setup_g3_env.write_text("", encoding="utf-8")
os.environ["SETUP_ENV_FILE"] = str(setup_env)
os.environ["SETUP_G3_ENV_FILE"] = str(setup_g3_env)

from core import state, sales_store  # noqa: E402

database_directory = tempfile.TemporaryDirectory(prefix="contacts-browser-")
state.DB_PATH = sales_store.DB_PATH = Path(database_directory.name) / "company.db"
state.init_db()
sales_store.init_sales_db()
fixture_org = state.create_org("Browser Studio", "browser-studio", domain="studio.test")
state.set_org_capabilities(fixture_org["id"], {"sales_prospecting": True})
state.set_active_org(fixture_org["id"])

records = [
    ("Alex Carter", "Founder", "Rift Dynamics", "alex@rift.test", "valid", "website"),
    ("Priya Shah", "Head of Operations", "Luma Logistics", "priya@luma.test", "valid", "linkedin"),
    ("Daniel Kim", "CTO", "Kairo Tech", "daniel@kairo.test", "valid", "conference"),
    ("Elena Ruiz", "Head of Growth", "Meridian Labs", "elena@meridian.test", None, "website"),
    ("James Okoro", "Founder", "Fieldworks", "james@fieldworks.test", "valid", "linkedin"),
    ("Maria Kowalski", "VP Engineering", "TerraBuild", "maria@terra.test", None, "referral"),
    ("Sophie Lee", "Head of R&D", "Northstar Labs", None, None, "research"),
    ("Nathan Park", "CEO", "Vector AI", "nathan@vector.test", "valid", "outbound"),
    ("Julia Lopez", "VP Commercial", "Catalyst Bio", "julia@catalyst.test", "valid", "website"),
    ("Ryan Tan", "Head of IT", "Orion Systems", "ryan@orion.test", "invalid", "linkedin"),
    ("Maya Chen", "Director", "Atlas Works", "maya@atlas.test", None, "manual"),
    ("Noah Williams", "CEO", "Beacon Health", "noah@beacon.test", None, "website"),
]
domains = [
    "rift.test", "luma.test", "kairo.test", "meridian.test", "fieldworks.test",
    "terra.test", "northstar.test", "vector.test", "catalyst.test", "orion.test",
    "atlas.test", "beacon.test",
]
industries = ["Software", "Logistics", "AI / ML", "Data & Analytics", "Consulting", "Construction", "Biotech", "Infrastructure"]

first_id = ""
for index, (name, role, company, email, verification, source) in enumerate(records):
    lead, _ = sales_store.upsert_lead({
        "full_name": name, "job_title": role, "company": company,
        "company_domain": domains[index],
        "email": email, "verification_status": verification, "source": source,
        "message": "Interested in a product walkthrough." if index == 0 else None,
    })
    if index < 8:
        sales_store.upsert_company_profile(
            domains[index], provider="test", status="resolved", company_name=company,
            summary={
                "industry": industries[index],
                "employee_range": "50–200" if index < 5 else "10–50",
                "location": {"country": "United States"},
                "description": "Operations software for distributed teams." if index == 0 else f"{company} is a saved company profile.",
                "website": f"https://{domains[index]}",
            },
        )
    if index == 0:
        first_id = lead["id"]
        sales_store.add_interaction(first_id, "inbound", "email", "inquiry", "Product walkthrough", "Please share details")
    if index == 9:
        sales_store.suppress_lead(lead["id"], "test_fixture")

with sales_store.connect() as connection:
    for index, (name, *_rest) in enumerate(records):
        stamp = f"2026-09-23T10:{59 - index:02}:00+00:00"
        connection.execute("UPDATE sales_leads SET created_at = ?, updated_at = ? WHERE full_name = ?", (stamp, stamp, name))
        connection.execute("UPDATE sales_company_profiles SET updated_at = ?, fetched_at = ? WHERE domain = ?", (stamp, stamp, domains[index]))
    connection.execute("UPDATE sales_interactions SET created_at = ?", ("2026-09-23T10:00:00+00:00",))


async def fixture_draft(lead):
    from agents.sales import OutreachDraft
    return OutreachDraft(
        subject=f"Introduction to {lead.get('company') or 'your team'}",
        body="Hello, I would welcome a short conversation about your current priorities and whether we can help.",
        rationale="Browser test provider substitute.", call_to_action="reply",
    )


import agents.sales  # noqa: E402

agents.sales.draft_outreach = fixture_draft


def fixture_company_profile(lead_id, provider="auto", force=False):
    lead = sales_store.get_lead(lead_id)
    if not lead:
        raise ValueError("lead not found")
    domain = lead.get("company_domain")
    if not domain:
        raise ValueError("company domain not found")
    profile = sales_store.upsert_company_profile(
        domain, provider="test", status="resolved", company_name=lead.get("company"),
        summary={"industry": "Professional services", "employee_range": "20–100", "location": {"country": "United States"}, "description": "Profile resolved during browser validation."},
    )
    return {"ok": True, "cached": False, "provider": "test", "domain": domain,
            "lead": sales_store.get_lead(lead_id), "company_profile": profile, "attempts": []}


import app.sales_api  # noqa: E402

app.sales_api.resolve_company_profile = fixture_company_profile

from app.api import app  # noqa: E402
import uvicorn  # noqa: E402

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8788, log_level="warning")
