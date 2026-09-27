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

from app.api import app  # noqa: E402
import uvicorn  # noqa: E402

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8791, log_level="warning")
