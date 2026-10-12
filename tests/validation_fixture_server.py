"""Real FastAPI with a fixed Hermes plan for the market-validation browser test.

Only the model call is substituted. Governance, the workflow store, and the
workflow runner are real, so the browser test walks the same code path production
uses, up to the single simulated action.
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.update({
    "DASHBOARD_USER": "founder", "DASHBOARD_PASSWORD": "browser-secret",
    "SALES_ACTION_TOKEN": "browser-action", "SALES_SEND_RECONCILE_ON_STARTUP": "false",
    "RATE_LIMIT_ENABLED": "false",
})

from core import state, workflow_store  # noqa: E402

storage = tempfile.TemporaryDirectory(prefix="validation-browser-")
state.DB_PATH = Path(storage.name) / "company.db"
workflow_store.DB_PATH = Path(storage.name) / "workflows.db"
state.init_db()

from tests.market_validation_fixtures import NORTHLIGHT_PLAN  # noqa: E402

FIXTURE_PLAN = NORTHLIGHT_PLAN


import agents.hermes as hermes  # noqa: E402
import app.onboarding_api as onboarding_api  # noqa: E402


async def fixture_strategy_draft(program):
    """Stand in for the AI strategy draft: no provider call in browser tests."""
    context = program.company_context
    industry = (context.industry if context else None) or "Logistics"
    return onboarding_api.StrategyInput(
        name="Northlight Ops first program", objective=program.company.objective,
        success_metric="Qualified replies per month", offers=["Operations audit"],
        icp=onboarding_api.Icp(industry=industry, description="Midmarket operations teams with manual handoffs", company_sizes=["20-200 employees"]),
        buyer_titles=["Operations Director"], markets=[program.company.market],
        positive_signals=["Growing operations team"], exclusions=["Outside the primary market"],
        tone="Direct and factual", approved_claims=["Operations workflow support"],
        prohibited_claims=["Guaranteed revenue"], channels=["email"],
    )


onboarding_api._generate_strategy_draft = fixture_strategy_draft


def fixture_plan_market_validation(context):
    """Stand in for Hermes: same grounding rule, same provenance shape, no provider."""
    from core.models import ROUTES
    from core.validation_plan import (
        WORKFLOW_TEMPLATE, GroundingReport, PlanProvenance, ValidationPlan, enforce_grounding,
    )

    assert context.state.marketing_stage == "starting_from_zero"
    plan, grounding = enforce_grounding(ValidationPlan.model_validate(FIXTURE_PLAN), context)
    return hermes.HermesPlanResult(
        plan=plan,
        provenance=PlanProvenance(
            prompt_version=WORKFLOW_TEMPLATE,
            prompt_path="prompts/market_validation_v1.md",
            context_updated_at=context.updated_at,
            model_route="reasoning",
            model_name=ROUTES["reasoning"],
            model_provider="omniroute",
        ),
        grounding=grounding,
    )


async def fixture_plan(*args, **kwargs):
    return fixture_plan_market_validation(*args, **kwargs)


hermes.plan_market_validation = fixture_plan

from app.api import app  # noqa: E402
import uvicorn  # noqa: E402

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8792, log_level="warning")