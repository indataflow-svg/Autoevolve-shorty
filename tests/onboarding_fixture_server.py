"""Real FastAPI and isolated stores with test-only provider substitutes."""

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
    "RATE_LIMIT_ENABLED": "false", "CE_API_KEY": "fixture-only",
})

from core import marketing_store, ops_store, sales_store, state  # noqa: E402

storage = tempfile.TemporaryDirectory(prefix="onboarding-browser-")
database = Path(storage.name) / "company.db"
state.DB_PATH = sales_store.DB_PATH = marketing_store.DB_PATH = ops_store.DB_PATH = database
state.init_db()
sales_store.init_sales_db()
marketing_store.init_marketing_db()
ops_store.init_db()


class FixtureCompanyEnrich:
    def enrich_company(self, domain):
        assert domain == "studio.test"
        return {"name": "Example Studio"}

    def extract_company_profile(self, payload):
        return {
            "name": payload["name"], "description": "Example Studio builds operations tools for teams.",
            "industry": "Software", "signals": {"summary_line": "Clear operations workflows"},
            "specialties": ["Workflow audit"],
        }


import services.company_enrich  # noqa: E402
services.company_enrich.CompanyEnrichClient = FixtureCompanyEnrich

import app.onboarding_api as onboarding  # noqa: E402


async def fixture_extract_domain(domain, max_pages):
    assert domain.rstrip("/") == "https://studio.test" and max_pages == 4
    return {
        "domain": "studio.test", "base_url": domain, "pages_ok": 1,
        "pages": [{"ok": True, "url": domain, "site_name": "Example Studio",
                   "description": "Example Studio builds operations tools for teams.", "text": ""}],
    }


onboarding.extract_domain = fixture_extract_domain


async def fixture_strategy_draft(program):
    assert program.company_context and program.company_context.industry == "Software"
    return onboarding.StrategyInput(
        name="Example Studio first program", objective=program.company.objective,
        success_metric="Qualified replies per month", offers=["Workflow audit"],
        icp=onboarding.Icp(industry="Software", description="Midmarket operations teams with manual handoffs", company_sizes=["50-500 employees"]),
        buyer_titles=["Operations Director"], markets=[program.company.market],
        positive_signals=["Growing operations team"], exclusions=["Outside the primary market"],
        tone="Direct and factual", approved_claims=["Operations workflow support"],
        prohibited_claims=["Guaranteed revenue"], channels=["email"],
    )


onboarding._generate_strategy_draft = fixture_strategy_draft


def fixture_research(*, industry, location, limit_per_provider):
    assert industry == "Software" and location == "United States" and limit_per_provider == 3
    rows = []
    for name, domain, country in [
        ("Acme Systems", "acme.test", "United States"),
        ("Other Systems", "other.test", "Canada"),
    ]:
        lead, _ = sales_store.upsert_lead({
            "company": name, "company_domain": domain, "country": country,
            "source": "prospeo", "metadata": {"company_candidate": True},
        })
        rows.append({"lead": lead})
    return {"results": rows, "providers": {"prospeo": 2}, "warnings": []}


def fixture_import(domain, *, limit, provider):
    assert domain == "acme.test" and limit == 1 and provider in {"hunter", "apollo"}
    lead, _ = sales_store.upsert_lead({
        "full_name": "Buyer One", "email": "buyer@acme.test", "job_title": "Operations Director",
        "company": "Acme Systems", "company_domain": domain, "source": provider,
    })
    return [{"lead": lead}]


async def fixture_draft(lead_id):
    return sales_store.create_draft(lead_id, "A real draft", "Hello, this is a saved draft for review.")


onboarding.research_market_leads = fixture_research
onboarding.import_domain = fixture_import
onboarding.build_draft = fixture_draft

import app.service_discovery_api as service_discovery  # noqa: E402


async def fixture_service_plan(service, company_context):
    assert service == "Appointment scheduling for dental clinics"
    return service_discovery.ServiceSearchPlan(
        buyer_industry="Dental clinics", search_keywords=["dental practice", "appointment scheduling"],
        buyer_titles=["Practice Manager"],
        rationale="Dental clinics may need help with appointment scheduling.",
    )


def fixture_service_search(*, keywords, buyer_titles, market, desired_contacts):
    assert buyer_titles and 1 <= desired_contacts <= 25
    if keywords[0] == "Veterinary clinics":
        return {"results": [], "providers": {"prospeo": 0}, "completed_providers": ["prospeo"], "warnings": []}
    assert keywords[0] == "Dental clinics"
    results = []
    for name, company, domain, provider in [
        ("Alex Lee", "Bright Dental", "bright.test", "apollo"),
        ("Sam Rivera", "Clear Dental", "clear.test", "prospeo"),
    ][:desired_contacts]:
        lead, _ = sales_store.upsert_lead({
            "full_name": name, "job_title": "Practice Manager", "company": company,
            "company_domain": domain, "country": market or "United States", "source": provider,
            "metadata": {"service_discovery_preview": True},
        })
        results.append(lead)
    return {"results": results, "providers": {"apollo": 1, "prospeo": 1}, "completed_providers": ["apollo", "prospeo"], "warnings": []}


service_discovery._plan_service = fixture_service_plan
service_discovery.search_service_contacts = fixture_service_search

from app.api import app  # noqa: E402
import uvicorn  # noqa: E402

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8791, log_level="warning")
