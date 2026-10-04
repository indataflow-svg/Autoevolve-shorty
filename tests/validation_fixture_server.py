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