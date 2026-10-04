"""Market validation: prompt construction, Hermes boundary, plan schema, storage, API.

Hermes is exercised through pydantic-ai's in-process ``FunctionModel`` so the
structured-output path is real while no provider is called and no marketing
action can happen.
"""

import asyncio
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

import core.state as state
from agents import hermes
from core.models import ROUTES
from agents.hermes import (
    CONTEXT_TOKEN,
    HermesError,
    HermesOutputError,
    build_instructions,
    plan_market_validation,
)
from app.api import app
from core.company_context import normalize_company_context, save_company_context
from core.validation_plan import (
    GROUNDING_THRESHOLD,
    WORKFLOW_TEMPLATE,
    GroundingReport,
    PlanProvenance,
    ValidationPlan,
    ValidationPlanRecord,
    build_plan_record,
    context_text,
    enforce_grounding,
    get_latest_validation_plan,
    get_validation_plan,
    grounding_ratio,
    init_validation_db,
    is_grounded,
    save_validation_plan,
)

NORTHLIGHT = {
    "company": {
        "name": "Northlight Ops",
        "description": "Northlight Ops runs a managed operations desk for small logistics teams.",
        "website": "https://northlight.example",
        "geography": "United States",
    },
    "product": {
        "name": "Managed Operations Desk",
        "description": "A guided setup and monthly review of the customer's operations handoffs.",
        "value_proposition": "Operations teams get a clean handoff record in one week.",
    },
    "customer": {
        "ideal_customer": "Logistics companies with 20-200 people running dispatch on spreadsheets",
        "industry": "Logistics",
        "buyer_roles": ["Operations Director", "Founder"],
    },
    "market": {
        "market": "United States",
        "problem": "Dispatch handoffs live in spreadsheets, so missed loads are found late.",
        "urgency": "Missed loads are charged back within the same week.",
        "alternatives": ["Spreadsheet templates", "Freight broker software"],
    },
    "evidence": {
        "existing_customers": ["Two design partners running the desk since March"],
        "testimonials": ["Operations Director, design partner: handoffs stopped falling through"],
        "traction": ["Two paid setups"],
    },
    "offer": {"description": "A two-week managed operations setup plus monthly review.", "pricing": "$4,000 setup plus $1,500 per month"},
    "resources": {"channels": ["Email", "LinkedIn"], "team": ["Founder"]},
    "constraints": {"operational": ["Founder writes all outbound personally"]},
    "objective": {"primary_goal": "Get the first ten paying customers"},
    "state": {"marketing_stage": "starting_from_zero"},
}

VALID_PLAN = {
    "workflow_template": WORKFLOW_TEMPLATE,
    "hypothesis": {
        "customer": "Logistics companies with 20-200 people running dispatch on spreadsheets",
        "problem": "Dispatch handoffs live in spreadsheets, so missed loads are found late",
        "trigger": "Missed loads are charged back within the same week",
        "offer": "A two-week managed operations setup plus monthly review",
        "reason_to_believe": "Two design partners running the desk since March",
        "desired_action": "Book a discovery call",
    },
    "market": {
        "target_customer": "Logistics companies with 20-200 people running dispatch on spreadsheets",
        "problem": "Dispatch handoffs live in spreadsheets, so missed loads are found late",
        "trigger": "Missed loads are charged back within the same week",
        "alternatives": "Spreadsheet templates and freight broker software",
    },
    "validation": {
        "method": "targeted_outbound",
        "channel": "email",
        "message": "I noticed your team runs dispatch on spreadsheets. How do you handle handoffs today?",
        "offer": "A two-week managed operations setup plus monthly review",
        "call_to_action": "Book a 20-minute discovery call",
        "validation_event": "Booked discovery call",
        "success_threshold": "At least 5 booked discovery calls from the first 50 targeted prospects",
        "time_window": "14 days",
    },
    "evidence": {
        "known_facts": ["Two design partners running the desk since March", "Two paid setups"],
        "assumptions": ["Operations directors will pay $4,000 for a setup"],
        "unknowns": ["How many similar companies run dispatch on spreadsheets"],
    },
    "reasoning": "The founder already writes outbound personally and has no paid budget, so targeted email is the fastest measurable test.",
    "next_action": "Review the plan and approve or reject the experiment",
    "limits": {"max_spend_usd": 0, "max_outreach_contacts": 50, "channel": "email", "duration_days": 14, "requires_approval": True},
}


def function_model(payload: dict):
    """An in-process pydantic-ai model that answers with one structured object.

    Using pydantic-ai's own FunctionModel exercises the real output validation and
    retry behaviour while calling no provider.
    """
    def respond(messages, info: AgentInfo):
        name = info.output_tools[0].name if info.output_tools else "final_result"
        return ModelResponse(parts=[ToolCallPart(tool_name=name, args=payload, tool_call_id="call_1")])

    return FunctionModel(function=respond)


class PromptTests(unittest.TestCase):
    """The versioned prompt and the canonical context it must receive."""

    def setUp(self):
        self.context = normalize_company_context(NORTHLIGHT)

    def test_prompt_is_a_versioned_file_with_one_context_slot(self):
        template = hermes.load_prompt_template()
        self.assertEqual(hermes.PROMPT_PATH.name, "market_validation_v1.md")
        self.assertEqual(hermes.PROMPT_VERSION, WORKFLOW_TEMPLATE)
        self.assertEqual(template.count(CONTEXT_TOKEN), 1)
        for heading in ("OBJECTIVE", "CONTEXT", "TASK", "METHOD", "RULES", "OUTPUT"):
            self.assertIn(heading, template)

    def test_context_is_supplied_as_the_canonical_object(self):
        instructions = build_instructions(self.context)
        self.assertNotIn(CONTEXT_TOKEN, instructions)
        payload = instructions.split("CONTEXT", 1)[1].split("TASK", 1)[0]
        supplied = json.loads(payload[payload.index("{"):payload.rindex("}") + 1])
        self.assertEqual(supplied, self.context.model_dump(mode="json"))
        self.assertEqual(supplied["state"]["marketing_stage"], "starting_from_zero")
        self.assertIsNone(supplied["product"]["category"])  # unanswered stays unknown


class PlanSchemaTests(unittest.TestCase):
    """The structured contract and the fact/assumption separation rule."""

    def test_valid_plan_parses_with_its_template_and_limits(self):
        plan = ValidationPlan.model_validate(VALID_PLAN)
        self.assertEqual(plan.workflow_template, WORKFLOW_TEMPLATE)
        self.assertEqual(plan.validation.method, "targeted_outbound")
        self.assertEqual(plan.limits.max_outreach_contacts, 50)
        self.assertTrue(plan.limits.requires_approval)

    def test_missing_required_fields_are_rejected(self):
        for missing in ("hypothesis", "market", "validation", "evidence", "reasoning", "next_action"):
            payload = {key: value for key, value in VALID_PLAN.items() if key != missing}
            with self.assertRaises(ValueError):
                ValidationPlan.model_validate(payload)
        thin = {**VALID_PLAN, "hypothesis": {**VALID_PLAN["hypothesis"], "trigger": ""}}
        with self.assertRaises(ValueError):
            ValidationPlan.model_validate(thin)

    def test_an_empty_evidence_ledger_is_rejected(self):
        with self.assertRaises(ValueError):
            ValidationPlan.model_validate({
                **VALID_PLAN, "evidence": {"known_facts": [], "assumptions": [], "unknowns": []},
            })

    def test_validation_method_is_not_a_closed_menu(self):
        plan = ValidationPlan.model_validate({
            **VALID_PLAN,
            "validation": {**VALID_PLAN["validation"], "method": "trade-show field conversations"},
        })
        self.assertEqual(plan.validation.method, "trade-show field conversations")

    def test_grounding_separates_the_founder_facts_from_inference(self):
        context = normalize_company_context(NORTHLIGHT)
        source = context_text(context)
        self.assertTrue(is_grounded("Two design partners running the desk since March", source))
        self.assertFalse(is_grounded("We surveyed 400 logistics directors in Germany", source))
        self.assertAlmostEqual(grounding_ratio("Two paid setups", source), 1.0)

        invented = ValidationPlan.model_validate({
            **VALID_PLAN,
            "evidence": {
                "known_facts": ["Two paid setups", "We won the 2025 logistics innovation award"],
                "assumptions": ["Operations directors will pay $4,000 for a setup"],
                "unknowns": ["How many similar companies run dispatch on spreadsheets"],
            },
        })
        grounded, report = enforce_grounding(invented, context)
        self.assertEqual(grounded.evidence.known_facts, ["Two paid setups"])
        self.assertIn("We won the 2025 logistics innovation award", grounded.evidence.assumptions)
        self.assertEqual(report.checked_facts, 2)
        self.assertEqual(len(report.moved_to_assumptions), 1)

    def test_fully_grounded_plans_are_left_alone(self):
        context = normalize_company_context(NORTHLIGHT)
        plan = ValidationPlan.model_validate(VALID_PLAN)
        grounded, report = enforce_grounding(plan, context)
        self.assertEqual(grounded.evidence.known_facts, plan.evidence.known_facts)
        self.assertEqual(report.moved_to_assumptions, [])
        self.assertEqual(report.checked_facts, 2)


class HermesTests(unittest.TestCase):
    """The Hermes boundary: OmniRoute path, structured output, no tools."""

    def setUp(self):
        self.context = normalize_company_context(NORTHLIGHT)

    def test_hermes_runs_over_the_existing_omniroute_gateway(self):
        from core import models

        self.assertIs(hermes.cloud_model, models.cloud_model)
        model = models.cloud_model("reasoning")
        self.assertEqual(str(getattr(model, "model_name")), models.ROUTES["reasoning"])
        self.assertIn(models.OMNIROUTE_BASE_URL.rstrip("/"), str(getattr(model, "base_url")))

    def test_hermes_returns_a_validated_plan_with_provenance(self):
        with patch.object(hermes, "cloud_model", return_value=function_model(VALID_PLAN)) as cloud:
            result = asyncio.run(plan_market_validation(self.context))
        cloud.assert_called_once_with("reasoning")
        self.assertEqual(result.plan.validation.method, "targeted_outbound")
        self.assertEqual(result.provenance.generated_by, "hermes")
        self.assertEqual(result.provenance.prompt_version, WORKFLOW_TEMPLATE)
        self.assertEqual(result.provenance.prompt_path, "prompts/market_validation_v1.md")
        self.assertEqual(result.provenance.model_route, "reasoning")
        # Provenance records the model actually called rather than a fixed name.
        self.assertEqual(
            result.provenance.model_name,
            str(getattr(cloud.return_value, "model_name", ROUTES["reasoning"])),
        )
        # Provenance names the gateway, not the internal endpoint URL.
        self.assertEqual(result.provenance.model_provider, "omniroute")
        self.assertNotIn("://", result.provenance.model_provider)
        self.assertEqual(result.provenance.context_schema_version, 1)
        self.assertEqual(result.grounding.moved_to_assumptions, [])

    def test_hermes_demotes_untraceable_facts_before_returning(self):
        payload = json.loads(json.dumps(VALID_PLAN))
        payload["evidence"]["known_facts"] = [
            "Two paid setups", "Our NPS is 74 across nine design partners",
        ]
        with patch.object(hermes, "cloud_model", return_value=function_model(payload)):
            result = asyncio.run(plan_market_validation(self.context))
        self.assertEqual(result.plan.evidence.known_facts, ["Two paid setups"])
        self.assertIn("Our NPS is 74 across nine design partners", result.plan.evidence.assumptions)
        self.assertEqual(len(result.grounding.moved_to_assumptions), 1)

    def test_malformed_model_output_fails_instead_of_producing_a_fake_plan(self):
        # The real pydantic-ai structured-output path rejects an incomplete plan.
        with patch.object(hermes, "cloud_model", return_value=function_model({"workflow_template": WORKFLOW_TEMPLATE})):
            with self.assertRaises(HermesError):
                asyncio.run(plan_market_validation(self.context))
        # The defensive coercion rejects anything that is not a plan at all.
        for output in ("not a plan", json.dumps({"workflow_template": WORKFLOW_TEMPLATE}), [1, 2, 3], None):
            with self.assertRaises(HermesOutputError):
                hermes._coerce_plan(output)

    def test_a_missing_prompt_slot_is_a_hard_error(self):
        with patch.object(hermes, "load_prompt_template", return_value="no slot here"):
            with self.assertRaises(HermesError):
                build_instructions(self.context)

    def test_hermes_agent_is_built_without_tools(self):
        captured = {}

        class CapturingAgent:
            def __init__(self, model, **kwargs):
                captured["model"] = model
                captured["kwargs"] = kwargs

            async def run(self, request):
                captured["request"] = request

                class Result:
                    output = ValidationPlan.model_validate(VALID_PLAN)

                return Result()

        with patch.object(hermes, "cloud_model", return_value=function_model(VALID_PLAN)), \
             patch("pydantic_ai.Agent", CapturingAgent):
            asyncio.run(plan_market_validation(self.context))
        self.assertNotIn("tools", captured["kwargs"])
        self.assertIs(captured["kwargs"]["output_type"], ValidationPlan)
        self.assertIn(self.context.company.name, captured["kwargs"]["instructions"])
        self.assertIn("structured plan", captured["request"])


class ValidationPlanStoreTests(unittest.TestCase):
    """Persistence: a plan is stored once and reads back unchanged."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.old_state = state.DB_PATH
        state.DB_PATH = Path(self.temporary.name) / "company.db"
        state.init_db()

    def tearDown(self):
        state.DB_PATH = self.old_state
        self.temporary.cleanup()

    def _record(self) -> ValidationPlanRecord:
        return build_plan_record(
            ValidationPlan.model_validate(VALID_PLAN),
            PlanProvenance(
                prompt_version=WORKFLOW_TEMPLATE, prompt_path="prompts/market_validation_v1.md",
                model_route="reasoning", model_name="auto/best-reasoning", model_provider="omniroute",
            ),
            GroundingReport(checked_facts=2),
        )

    def test_plan_is_persisted_as_planned_and_reads_back(self):
        self.assertIsNone(get_latest_validation_plan())
        record = save_validation_plan(self._record())
        self.assertEqual(record.status, "planned")
        stored = get_validation_plan(record.id)
        self.assertEqual(stored.plan.model_dump(), record.plan.model_dump())
        self.assertEqual(stored.provenance.prompt_version, WORKFLOW_TEMPLATE)
        self.assertEqual(get_latest_validation_plan().id, record.id)

    def test_the_latest_plan_wins(self):
        first = save_validation_plan(self._record())
        second = save_validation_plan(self._record())
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(get_latest_validation_plan().id, second.id)

    def test_plan_history_survives_a_fresh_connection(self):
        record = save_validation_plan(self._record())
        init_validation_db()
        self.assertEqual(get_validation_plan(record.id).plan.workflow_template, WORKFLOW_TEMPLATE)


class ValidationApiTests(unittest.TestCase):
    """POST generates through Hermes; GET returns the stored plan. Nothing runs."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.old_state = state.DB_PATH
        state.DB_PATH = Path(self.temporary.name) / "company.db"
        state.init_db()
        self.env = patch.dict(os.environ, {
            "DASHBOARD_USER": "founder", "DASHBOARD_PASSWORD": "dashboard-secret",
            "SALES_ACTION_TOKEN": "action-secret", "SALES_SEND_RECONCILE_ON_STARTUP": "false",
        }, clear=False)
        self.env.start()
        self.client = TestClient(app)
        self.auth = ("founder", "dashboard-secret")
        self.headers = {"X-Founder-Action-Token": "action-secret"}
        self.context = normalize_company_context(NORTHLIGHT)
        save_company_context(self.context)

    def tearDown(self):
        self.env.stop()
        state.DB_PATH = self.old_state
        self.temporary.cleanup()

    def post_plan(self, **kwargs):
        return self.client.post("/company/marketing/validation/plan", auth=self.auth, headers=self.headers, **kwargs)

    def get_plan(self):
        return self.client.get("/company/marketing/validation/plan", auth=self.auth)

    @staticmethod
    def _result():
        return hermes.HermesPlanResult(
            plan=ValidationPlan.model_validate(VALID_PLAN),
            provenance=PlanProvenance(
                prompt_version=WORKFLOW_TEMPLATE, prompt_path="prompts/market_validation_v1.md",
                model_route="reasoning", model_name="auto/best-reasoning", model_provider="omniroute",
            ),
            grounding=GroundingReport(checked_facts=2),
        )

    def test_post_generates_and_persists_a_plan_and_get_returns_it(self):
        with patch.object(hermes, "plan_market_validation", return_value=self._result()) as generate:
            response = self.post_plan()
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["status"], "planned")
        self.assertEqual(body["plan"]["workflow_template"], WORKFLOW_TEMPLATE)
        self.assertEqual(body["plan"]["validation"]["method"], "targeted_outbound")
        self.assertEqual(body["provenance"]["generated_by"], "hermes")
        self.assertEqual(body["plan"]["limits"]["requires_approval"], True)
        generate.assert_awaited_once()
        stored = self.get_plan()
        self.assertEqual(stored.status_code, 200, stored.text)
        self.assertEqual(stored.json()["id"], body["id"])

    def test_get_before_any_plan_is_a_clear_404(self):
        self.assertEqual(self.get_plan().status_code, 404)
        self.assertIn("no validation plan", self.get_plan().json()["detail"])

    def test_generation_requires_the_founder_token(self):
        denied = self.client.post("/company/marketing/validation/plan", auth=self.auth)
        self.assertEqual(denied.status_code, 403)
        unauthenticated = self.client.get("/company/marketing/validation/plan")
        self.assertEqual(unauthenticated.status_code, 401)
        self.assertIsNone(get_latest_validation_plan())

    def test_missing_context_cannot_be_planned(self):
        from core.company_context import clear_company_context

        clear_company_context()
        response = self.post_plan()
        self.assertEqual(response.status_code, 409)
        self.assertIn("onboarding", response.json()["detail"])
        self.assertIsNone(get_latest_validation_plan())

    def test_incomplete_context_is_refused_rather_than_invented(self):
        save_company_context(normalize_company_context({
            "company": {"name": "Northlight Ops"},
            "state": {"marketing_stage": "starting_from_zero"},
        }))
        response = self.post_plan()
        self.assertEqual(response.status_code, 422)
        self.assertIn("incomplete", response.json()["detail"])
        self.assertIsNone(get_latest_validation_plan())

    def test_unsupported_marketing_stage_is_reported_not_routed(self):
        stored = self.context.model_dump(mode="json")
        stored["state"]["marketing_stage"] = "already_running_campaigns"
        init_validation_db()
        with state.connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO company_context (id, schema_version, context_json, created_at, updated_at) "
                "VALUES (1, 1, ?, ?, ?)",
                (json.dumps(stored), "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"),
            )
        response = self.post_plan()
        self.assertEqual(response.status_code, 409)
        self.assertIn("already_running_campaigns", response.json()["detail"])
        self.assertIsNone(get_latest_validation_plan())

    def test_hermes_failures_never_produce_a_plan(self):
        with patch.object(hermes, "plan_market_validation", side_effect=HermesOutputError("bad schema")):
            malformed = self.post_plan()
        self.assertEqual(malformed.status_code, 502)
        self.assertIn("valid validation plan", malformed.json()["detail"])

        with patch.object(hermes, "plan_market_validation", side_effect=RuntimeError("Model router is not configured")):
            unconfigured = self.post_plan()
        self.assertEqual(unconfigured.status_code, 409)

        with patch.object(hermes, "plan_market_validation", side_effect=ConnectionError("omni route down")):
            gateway = self.post_plan()
        self.assertEqual(gateway.status_code, 502)
        self.assertIn("omni route down", gateway.json()["detail"])
        self.assertIsNone(get_latest_validation_plan())

    def test_a_plan_that_cannot_be_saved_is_not_reported_as_saved(self):
        from app import validation_api

        with patch.object(hermes, "plan_market_validation", return_value=self._result()), \
             patch.object(validation_api, "save_validation_plan", side_effect=sqlite3.OperationalError("disk full")):
            response = self.post_plan()
        self.assertEqual(response.status_code, 500)
        self.assertIn("could not be saved", response.json()["detail"])
        self.assertIsNone(get_latest_validation_plan())

    def test_planning_starts_no_workflow_campaign_or_task(self):
        from core import workflow_store

        old_workflows = workflow_store.DB_PATH
        workflow_store.DB_PATH = Path(self.temporary.name) / "workflows.db"
        try:
            with patch.object(hermes, "plan_market_validation", return_value=self._result()):
                self.assertEqual(self.post_plan().status_code, 200)
            self.assertEqual(workflow_store.list_workflows(), [])
            self.assertEqual(state.get_recent_tasks(limit=20), [])
        finally:
            workflow_store.DB_PATH = old_workflows


class RoutingToValidationTests(unittest.TestCase):
    """The chain end to end: onboarding state routes into a planned record."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.old_state = state.DB_PATH
        state.DB_PATH = Path(self.temporary.name) / "company.db"
        state.init_db()
        self.env = patch.dict(os.environ, {
            "DASHBOARD_USER": "founder", "DASHBOARD_PASSWORD": "dashboard-secret",
            "SALES_ACTION_TOKEN": "action-secret", "SALES_SEND_RECONCILE_ON_STARTUP": "false",
        }, clear=False)
        self.env.start()
        self.client = TestClient(app)
        self.auth = ("founder", "dashboard-secret")
        self.headers = {"X-Founder-Action-Token": "action-secret"}

    def tearDown(self):
        self.env.stop()
        state.DB_PATH = self.old_state
        self.temporary.cleanup()

    def test_onboarding_to_market_validation_to_persisted_plan(self):
        started = self.client.post("/company/setup/onboarding/company", auth=self.auth, headers=self.headers, json={
            "name": "Northlight Ops", "website": "https://northlight.example",
            "objective": "Get the first ten paying customers", "market": "United States",
        })
        self.assertEqual(started.status_code, 200, started.text)
        confirmed = self.client.post("/company/setup/onboarding/company/confirm", auth=self.auth, headers=self.headers, json={
            "name": "Northlight Ops", "website": "https://northlight.example",
            "description": "Northlight Ops runs a managed operations desk for small logistics teams.",
            "industry": "Logistics", "positioning": "Operations teams get a clean handoff record in one week.",
            "offer_summary": "A two-week managed operations setup plus monthly review.",
            "product_name": "Managed Operations Desk",
            "product_description": "A guided setup and monthly review of the customer's operations handoffs.",
            "ideal_customer": "Logistics companies with 20-200 people running dispatch on spreadsheets",
            "buyer_roles": ["Operations Director", "Founder"],
            "problem": "Dispatch handoffs live in spreadsheets, so missed loads are found late.",
            "urgency": "Missed loads are charged back within the same week.",
            "alternatives": ["Spreadsheet templates", "Freight broker software"],
            "existing_customers": ["Two design partners running the desk since March"],
            "testimonials": ["Operations Director, design partner: handoffs stopped falling through"],
            "traction": ["Two paid setups"],
            "pricing": "$4,000 setup plus $1,500 per month",
            "channels": ["Email", "LinkedIn"],
            "team": ["Founder"],
            "operational_constraints": ["Founder writes all outbound personally"],
            "marketing_stage": "starting_from_zero",
        })
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        view = confirmed.json()
        self.assertEqual(view["marketing_stage"], "starting_from_zero")
        self.assertEqual(view["next_stage"], "market_validation")

        result = hermes.HermesPlanResult(
            plan=ValidationPlan.model_validate(VALID_PLAN),
            provenance=PlanProvenance(
                prompt_version=WORKFLOW_TEMPLATE, prompt_path="prompts/market_validation_v1.md",
                model_route="reasoning", model_name="auto/best-reasoning", model_provider="omniroute",
            ),
            grounding=GroundingReport(checked_facts=2),
        )
        with patch.object(hermes, "plan_market_validation", return_value=result) as generate:
            planned = self.client.post(
                "/company/marketing/validation/plan", auth=self.auth, headers=self.headers,
            )
        self.assertEqual(planned.status_code, 200, planned.text)
        # Hermes received exactly the persisted context, nothing else.
        supplied = generate.await_args.args[0]
        self.assertEqual(supplied.state.marketing_stage, "starting_from_zero")
        self.assertEqual(supplied.evidence.traction, ["Two paid setups"])
        self.assertEqual(supplied.constraints.operational, ["Founder writes all outbound personally"])
        self.assertEqual(planned.json()["status"], "planned")
        self.assertEqual(get_latest_validation_plan().status, "planned")


if __name__ == "__main__":
    unittest.main()