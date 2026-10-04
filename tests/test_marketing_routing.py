"""Starting-state routing: CompanyContext state -> initial route -> dashboard."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

import core.state as state
from app.api import app
from core.company_context import (
    ContextState,
    init_context_db,
    normalize_company_context,
    save_company_context,
)
from core.marketing_routing import (
    INITIAL_ROUTES,
    RouteState,
    UnsupportedMarketingStage,
    resolve_initial_route,
    route_for_stage,
    route_state_for,
)


class InitialRouteTests(unittest.TestCase):
    """The routing decision itself: one stage in, one route out, or a clear error."""

    def test_starting_from_zero_routes_to_market_validation(self):
        route = route_for_stage("starting_from_zero")
        self.assertEqual(route.marketing_stage, "starting_from_zero")
        self.assertEqual(route.next_stage, "market_validation")
        self.assertEqual(route.label, "Market Validation")
        self.assertIn("market-validation experiment", route.summary)

    def test_route_comes_from_the_stored_context_state(self):
        context = normalize_company_context({
            "company": {"name": "Example Studio"},
            "state": {"marketing_stage": "Starting from zero"},
        })
        self.assertEqual(resolve_initial_route(context).next_stage, "market_validation")

    def test_an_unknown_stage_raises_instead_of_defaulting(self):
        for stage in ("running_campaigns", "unknown", "starting_from_zeroo"):
            with self.assertRaises(UnsupportedMarketingStage) as caught:
                route_for_stage(stage)
            self.assertIn(stage, str(caught.exception))
            # The rejected stage must never resolve to the first branch.
            self.assertIsNone(route_state_for(staged_context(stage)).next_stage)
            self.assertIn(stage, route_state_for(staged_context(stage)).routing_error)

    def test_a_stage_beyond_this_phase_is_not_silently_routed(self):
        # A record written before a stage was understood must not be mapped onto
        # the first branch; the resolver says so and read models surface it.
        context = normalize_company_context({"state": {"marketing_stage": "starting_from_zero"}})
        stored = context.model_copy(update={
            "state": ContextState.model_construct(marketing_stage="already_running_campaigns"),
        })
        with self.assertRaises(UnsupportedMarketingStage):
            resolve_initial_route(stored)
        unresolved = route_state_for(stored)
        self.assertIsNone(unresolved.next_stage)
        self.assertIn("already_running_campaigns", unresolved.routing_error)

    def test_a_missing_stage_or_context_reports_why_there_is_no_route(self):
        with self.assertRaises(UnsupportedMarketingStage):
            route_for_stage(None)
        with self.assertRaises(LookupError):
            resolve_initial_route(None)
        with self.assertRaises(LookupError):
            resolve_initial_route({"state": {"marketing_stage": "starting_from_zero"}})
        self.assertIsNone(route_state_for(None).routing_error)
        self.assertIsNone(route_state_for(normalize_company_context({})).routing_error)

    def test_only_the_starting_from_zero_branch_exists(self):
        self.assertEqual([route.marketing_stage for route in INITIAL_ROUTES], ["starting_from_zero"])
        self.assertEqual({route.next_stage for route in INITIAL_ROUTES}, {"market_validation"})

    def test_route_state_flattens_a_resolved_route(self):
        context = normalize_company_context({"state": {"marketing_stage": "starting_from_zero"}})
        self.assertEqual(
            RouteState.resolved(resolve_initial_route(context)).model_dump(),
            {
                "marketing_stage": "starting_from_zero",
                "next_stage": "market_validation",
                "route_label": "Market Validation",
                "route_summary": "AutoEvolve is preparing your first market-validation experiment.",
                "routing_error": None,
            },
        )


def staged_context(stage: str | None):
    """A context-shaped object for stage-level routing checks."""
    return SimpleNamespace(state=SimpleNamespace(marketing_stage=stage))


class RoutingApiTests(unittest.TestCase):
    """The route travels with the context, the onboarding view, and Home."""

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

    def onboarding(self, suffix: str, payload: dict | None = None):
        return self.client.post(
            f"/company/setup/onboarding/{suffix}", auth=self.auth, headers=self.headers, json=payload,
        )

    def confirm_onboarding(self, **extra):
        started = self.onboarding("company", {
            "name": "Example Studio", "website": "https://studio.test",
            "objective": "Get first customers", "market": "United States",
        })
        self.assertEqual(started.status_code, 200, started.text)
        payload = {
            "name": "Example Studio", "website": "https://studio.test",
            "description": "Example Studio builds operations tools.",
            "industry": "Software", "positioning": "Operations teams get clear records.",
            "offer_summary": "A guided operations workflow.",
            "product_name": "Ops Audit", "ideal_customer": "Midmarket operations teams",
            "problem": "Handoffs are manual", "marketing_stage": "starting_from_zero",
        } | extra
        return self.onboarding("company/confirm", payload)

    def test_before_onboarding_there_is_no_route(self):
        body = self.client.get("/company/context", auth=self.auth).json()
        self.assertEqual(body["status"], "context_incomplete")
        self.assertIsNone(body["marketing_stage"])
        self.assertIsNone(body["next_stage"])
        self.assertIsNone(body["routing_error"])

    def test_confirming_onboarding_exposes_the_resolved_route(self):
        confirmed = self.confirm_onboarding()
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        body = confirmed.json()
        self.assertEqual(body["marketing_stage"], "starting_from_zero")
        self.assertEqual(body["next_stage"], "market_validation")
        self.assertEqual(body["route_label"], "Market Validation")
        self.assertFalse(body["onboarding_complete"])  # not activated yet

        read = self.client.get("/company/context", auth=self.auth).json()
        self.assertEqual(read["status"], "context_complete")
        self.assertEqual(read["marketing_stage"], "starting_from_zero")
        self.assertEqual(read["next_stage"], "market_validation")
        self.assertEqual(read["context"]["state"]["marketing_stage"], "starting_from_zero")

    def test_completed_onboarding_reports_complete_and_the_route(self):
        self.confirm_onboarding()
        program = {
            "id": "program_routing", "status": "activated", "activated_at": "2026-01-01T00:00:00+00:00",
            "company": {"name": "Example Studio", "website": "https://studio.test",
                        "objective": "Get first customers", "market": "United States"},
            "company_context": {
                "name": "Example Studio", "website": "https://studio.test",
                "description": "Example Studio builds operations tools.",
                "industry": "Software", "positioning": "Operations teams get clear records.",
                "offer_summary": "A guided operations workflow.",
            },
        }
        state.save_onboarding_program(program)
        view = self.client.get("/company/ui/onboarding", auth=self.auth).json()
        self.assertTrue(view["onboarding_complete"])
        self.assertEqual(view["next_step"], "home")
        self.assertEqual(view["marketing_stage"], "starting_from_zero")
        self.assertEqual(view["next_stage"], "market_validation")

        home = self.client.get("/company/ui/home", auth=self.auth).json()
        self.assertEqual(home["onboarding_status"], "activated")
        self.assertEqual(home["marketing_stage"], "starting_from_zero")
        self.assertEqual(home["next_stage"], "market_validation")
        self.assertEqual(home["route_label"], "Market Validation")

    def test_dashboard_reports_no_route_before_a_starting_state_exists(self):
        home = self.client.get("/company/ui/home", auth=self.auth).json()
        self.assertIsNone(home["next_stage"])
        self.assertIsNone(home["route_label"])

    def test_dashboard_reports_the_error_for_an_unsupported_stored_state(self):
        stored = normalize_company_context({
            "company": {"name": "Example Studio"}, "state": {"marketing_stage": "starting_from_zero"},
        }).model_dump(mode="json")
        # Simulate a record written by a build that understood a stage this one
        # cannot route. Written as raw JSON so the read path is what is tested.
        stored["state"]["marketing_stage"] = "already_running_campaigns"
        init_context_db()
        with state.connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO company_context "
                "(id, schema_version, context_json, created_at, updated_at) VALUES (1, 1, ?, ?, ?)",
                (json.dumps(stored), "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"),
            )
        body = self.client.get("/company/context", auth=self.auth).json()
        self.assertIsNone(body["next_stage"])
        self.assertIsNone(body["route_label"])
        self.assertIn("already_running_campaigns", body["routing_error"])
        home = self.client.get("/company/ui/home", auth=self.auth).json()
        self.assertIsNone(home["next_stage"])
        self.assertIn("already_running_campaigns", home["routing_error"])

    def test_replacing_the_context_reresolves_the_route(self):
        self.confirm_onboarding()
        replaced = self.client.put("/company/context", auth=self.auth, headers=self.headers, json={
            "company": {"name": "Example Studio"},
            "objective": {"primary_goal": "Get first customers"},
            "state": {"marketing_stage": "Starting from zero"},
        })
        self.assertEqual(replaced.status_code, 200, replaced.text)
        self.assertEqual(replaced.json()["next_stage"], "market_validation")
        self.assertEqual(replaced.json()["marketing_stage"], "starting_from_zero")

    def test_routing_creates_no_workflow_and_executes_nothing(self):
        self.confirm_onboarding()
        response = self.client.get("/company/context", auth=self.auth)
        self.assertEqual(response.status_code, 200)
        # Reading state must not start a workflow, a task, or a campaign.
        for path in ("/company/workflows", "/company/ui/home"):
            self.assertEqual(self.client.get(path, auth=self.auth).status_code, 200)
        self.assertEqual(state.get_recent_tasks(limit=10), [])


if __name__ == "__main__":
    unittest.main()