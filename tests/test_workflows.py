"""Workflow layer tests (implementation.md §16).

The runner and adapters are exercised against a temporary Company Core
database. External engines (G1 strategy, G2 media, G3 publishing, sales
analytics) are substituted at their existing service boundary through
``services.marketing_worker`` and ``core.sales_store``; the workflow
architecture itself is never faked.
"""

import json
import sys
import tempfile
import types
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch


if "dotenv" not in sys.modules:
    try:
        import dotenv  # noqa: F401
    except ImportError:
        module = types.ModuleType("dotenv")
        module.dotenv_values = lambda _path: {}
        sys.modules["dotenv"] = module

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.workflows_api import router as workflows_router
from core import marketing_store, state, workflow_store
from services import workflow_actions, workflow_runner


STEPS = [
    {"id": "strategy", "action": "g1_strategy"},
    {"id": "assets", "action": "generate_assets"},
    {"id": "publish", "action": "publish"},
    {"id": "collect", "action": "collect_results"},
    {"id": "evaluate", "action": "evaluate"},
]

CONCEPTS = [
    {
        "id": "c1", "buyer": "ops_manager", "pain": "manual handoffs",
        "thesis": "one record", "hook": "HANDOFFS NEED ONE RECORD", "narrative": "workflow",
        "cta": "walkthrough", "evidence_strength": 0.7, "buyer_relevance": 0.85, "product_fit": 0.8,
    },
    {
        "id": "c2", "buyer": "ops_manager", "pain": "missing ownership",
        "thesis": "clear ownership", "hook": "OWNERSHIP NEEDS A TRAIL", "narrative": "accountability",
        "cta": "walkthrough", "evidence_strength": 0.9, "buyer_relevance": 0.9, "product_fit": 0.95,
    },
    {
        "id": "c3", "buyer": "ops_manager", "pain": "split views",
        "thesis": "shared context", "hook": "CARGO NEEDS SHARED CONTEXT", "narrative": "visibility",
        "cta": "walkthrough", "evidence_strength": 0.8, "buyer_relevance": 0.88, "product_fit": 0.87,
    },
]


class WorkflowTestBase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self._original_paths = (workflow_store.DB_PATH, marketing_store.DB_PATH, state.DB_PATH)
        workflow_store.DB_PATH = self.base / "workflows.db"
        marketing_store.DB_PATH = self.base / "company.db"
        state.DB_PATH = self.base / "company.db"
        state.init_db()
        marketing_store.init_marketing_db()
        workflow_store.init_db()
        self.org = state.create_org("Example Company", "company-core", env_prefix="BUFFER_")

    def tearDown(self):
        workflow_store.DB_PATH, marketing_store.DB_PATH, state.DB_PATH = self._original_paths
        self.temporary.cleanup()

    def make_workflow(self, steps=None, **kwargs):
        return workflow_store.create_workflow(
            name=kwargs.pop("name", "InDataFlow Launch Experiment"),
            objective=kwargs.pop("objective", "Generate qualified demo conversations"),
            steps=steps if steps is not None else STEPS,
            trigger={"type": "manual", "config": {"org_id": self.org["id"], "topic": "freight docs"}},
            success_metric={"type": "conversion", "target": 0.1},
            **kwargs,
        )

    @staticmethod
    def fake_run_g1(campaign_id, **kwargs):
        marketing_store.update_campaign(campaign_id, g1_campaign_id="camp_test", g1_output_path="/tmp/g1.json")
        return {
            "campaign": {"campaign_id": "camp_test", "status": "ready_for_media", "quality": {"warnings": []}},
            "concepts": CONCEPTS,
            "selected_concept": CONCEPTS[1],
            "package_path": "/tmp/g1.json",
        }

    @staticmethod
    def fake_run_media(campaign_id, **kwargs):
        variant = marketing_store.create_variant(campaign_id, "shorts", "Voice-A", 1.0)
        marketing_store.update_variant(
            variant["id"], status="ready", video_path="/tmp/review.mp4",
            sha256="a" * 64, duration_seconds=24.0,
        )
        marketing_store.update_campaign(
            campaign_id, status="variants_ready", current_stage="founder_variant_review",
            asset_manifest_path="/tmp/asset_manifest.json",
        )

    @staticmethod
    def fake_run_g3(campaign_id, **kwargs):
        marketing_store.update_campaign(
            campaign_id, status="drafted", current_stage="buffer_review", g3_status="drafted",
            g3_result_json=json.dumps({
                "ok": True, "provider": "buffer", "publish_allowed": False,
                "results": [{"platform": "instagram", "status": "draft_confirmed", "post_id": "buf_1"}],
            }),
        )

    def patch_engines(self):
        return [
            patch("services.marketing_worker.run_g1", side_effect=self.fake_run_g1),
            patch("services.marketing_worker.run_media_pipeline", side_effect=self.fake_run_media),
            patch("services.marketing_worker.run_g3", side_effect=self.fake_run_g3),
        ]

    def patched(self, patcher_list):
        stack = ExitStack()
        for patcher in patcher_list:
            stack.enter_context(patcher)
        return stack


class WorkflowModelTests(WorkflowTestBase):
    def test_valid_workflow_is_created_ready_to_run(self):
        workflow = self.make_workflow()
        self.assertTrue(workflow.id.startswith("wf_"))
        self.assertEqual(workflow.state.status, "draft")
        self.assertEqual([step.action for step in workflow.steps], [
            "g1_strategy", "generate_assets", "publish", "collect_results", "evaluate",
        ])
        self.assertEqual(workflow_runner.validate_workflow(workflow), [])

    def test_invalid_workflow_reports_issues(self):
        workflow = self.make_workflow(steps=[
            {"id": "a", "action": "unknown_action"},
            {"id": "a", "action": "publish"},
        ])
        issues = workflow_runner.validate_workflow(workflow)
        self.assertTrue(any("unknown action" in issue for issue in issues))
        self.assertTrue(any("duplicate step id" in issue for issue in issues))

    def test_empty_workflow_is_invalid(self):
        workflow = workflow_store.create_workflow(name="Empty", steps=[])
        self.assertIn("workflow must define at least one step", workflow_runner.validate_workflow(workflow))

    def test_workflow_round_trips_through_storage(self):
        workflow = self.make_workflow()
        reloaded = workflow_store.get_workflow(workflow.id)
        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded.name, workflow.name)
        self.assertEqual(len(reloaded.steps), 5)


def stub_actions(calls, overrides=None):
    overrides = overrides or {}
    functions = {}
    for step in STEPS:
        name = step["action"]

        def make(action):
            def _fn(context, config):
                calls.append(action)
                if action in overrides:
                    return overrides[action](context, config)
                return {"status": "completed", "output": {}}

            return _fn

        functions[name] = make(name)
    return functions


def patchers(functions):
    return [patch.object(workflow_actions, name, fn) for name, fn in functions.items()]


class WorkflowRunnerTests(WorkflowTestBase):
    def test_steps_execute_in_order_and_state_is_persisted(self):
        calls = []
        workflow = self.make_workflow()
        with self.patched(patchers(stub_actions(calls))):
            finished = workflow_runner.run_workflow(workflow.id)
        self.assertEqual(calls, ["g1_strategy", "generate_assets", "publish", "collect_results", "evaluate"])
        self.assertEqual(finished.state.status, "completed")
        self.assertIsNone(finished.state.current_step)
        reloaded = workflow_store.get_workflow(workflow.id)
        self.assertEqual([item.step_id for item in reloaded.state.results], [step["id"] for step in STEPS])
        for execution in reloaded.state.results:
            self.assertEqual(execution.status, "completed")
            self.assertIsInstance(execution.duration_ms, int)
            self.assertTrue(execution.started_at and execution.finished_at)

    def test_failure_stops_execution_and_records_error(self):
        calls = []

        def boom(context, config):
            raise RuntimeError("g2 exploded")

        workflow = self.make_workflow()
        with self.patched(patchers(stub_actions(calls, {"generate_assets": boom}))):
            finished = workflow_runner.run_workflow(workflow.id)
        self.assertEqual(finished.state.status, "failed")
        self.assertIn("g2 exploded", finished.state.error or "")
        self.assertEqual(calls, ["g1_strategy", "generate_assets"])
        failed = [item for item in finished.state.results if item.step_id == "assets"]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0].status, "failed")

    def test_resume_does_not_repeat_completed_steps(self):
        calls = []
        attempts = {"assets": 0}

        def flaky_assets(context, config):
            attempts["assets"] += 1
            if attempts["assets"] == 1:
                raise RuntimeError("transient")
            return {"status": "completed", "output": {}}

        workflow = self.make_workflow()
        with self.patched(patchers(stub_actions(calls, {"generate_assets": flaky_assets}))):
            failed = workflow_runner.run_workflow(workflow.id)
            self.assertEqual(failed.state.status, "failed")
            resumed = workflow_runner.run_workflow(workflow.id, resume=True)
        self.assertEqual(resumed.state.status, "completed")
        self.assertEqual(calls.count("g1_strategy"), 1)
        self.assertEqual(calls.count("generate_assets"), 2)
        self.assertEqual([item.step_id for item in resumed.state.results if item.status == "completed"],
                         [step["id"] for step in STEPS])

    def test_terminal_workflow_is_not_rerun(self):
        calls = []
        workflow = self.make_workflow()
        with self.patched(patchers(stub_actions(calls))):
            workflow_runner.run_workflow(workflow.id)
            first = list(calls)
            workflow_runner.run_workflow(workflow.id)
        self.assertEqual(calls, first)

    def test_invalid_workflow_is_rejected_before_execution(self):
        workflow = workflow_store.create_workflow(
            name="Broken", steps=[{"id": "x", "action": "nope"}],
        )
        with self.assertRaises(workflow_runner.WorkflowValidationError):
            workflow_runner.run_workflow(workflow.id)


class WorkflowAdapterTests(WorkflowTestBase):
    def seed_campaign(self):
        task = state.create_task(
            org_id=self.org["id"], agent="growth", task_type="workflow_campaign", input_text="seed",
        )
        return marketing_store.create_campaign(
            org_id=self.org["id"], task_id=task["id"], request="seed", objective="awareness",
            buyer="ops_manager", topic="freight docs", social_platforms=["instagram"],
            video_platform="shorts",
        )

    def test_g1_strategy_creates_campaign_and_three_hypotheses(self):
        with self.patched(self.patch_engines()):
            result = workflow_actions.g1_strategy(
                {"workflow_id": "wf_test", "objective": "awareness"},
                {"org_id": self.org["id"], "topic": "freight docs"},
            )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["metrics"], {"hypotheses": 3})
        self.assertEqual(result["output"]["selected_hypothesis_id"], "c2")
        hypotheses = result["output"]["hypotheses"]
        self.assertEqual([item["id"] for item in hypotheses], ["c1", "c2", "c3"])
        self.assertEqual(hypotheses[0]["message"], "HANDOFFS NEED ONE RECORD")
        self.assertEqual(hypotheses[0]["audience"], "ops_manager")
        campaign = marketing_store.get_campaign(result["output"]["campaign_id"])
        self.assertEqual(campaign["org_id"], self.org["id"])

    def test_generate_assets_records_and_selects_ready_variant(self):
        campaign = self.seed_campaign()
        with self.patched(self.patch_engines()):
            result = workflow_actions.generate_assets({"campaign_id": campaign["id"]}, {})
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(result["output"]["assets"]), 1)
        stored = marketing_store.get_campaign(campaign["id"])
        self.assertEqual(stored["selected_variant_id"], result["output"]["selected_variant_id"])

    def test_publish_records_attribution_from_g3(self):
        campaign = self.seed_campaign()
        with self.patched(self.patch_engines()):
            workflow_actions.generate_assets({"campaign_id": campaign["id"]}, {})
            result = workflow_actions.publish(
                {"campaign_id": campaign["id"], "workflow_id": "wf_test"}, {},
            )
        self.assertEqual(result["status"], "completed")
        publication = result["output"]["publications"][0]
        self.assertEqual(publication["post_id"], "buf_1")
        self.assertEqual(publication["workflow_id"], "wf_test")
        self.assertEqual(publication["campaign_id"], campaign["id"])
        self.assertFalse(publication["publish_allowed"])

    def test_collect_results_reads_existing_sales_metrics(self):
        with patch("core.sales_store.summary", return_value={
            "total": 10, "by_stage": {"qualified": 3, "meeting": 1, "new": 6}, "by_source": {},
        }):
            result = workflow_actions.collect_results({"campaign_id": None}, {})
        metrics = result["output"]["results"]["metrics"]
        self.assertEqual(metrics["leads"], 10)
        self.assertEqual(metrics["qualified_leads"], 4)
        self.assertEqual(metrics["meetings"], 1)
        self.assertAlmostEqual(metrics["conversion"], 0.4)

    def test_evaluate_returns_winner_losers_and_next_action(self):
        hypotheses = workflow_actions.hypotheses_from_g1({"concepts": CONCEPTS})
        evaluation = workflow_actions.evaluate(
            {
                "hypotheses": hypotheses,
                "selected_hypothesis_id": "c2",
                "results": {"metrics": {"conversion": 0.2, "target": 0.1}},
            },
            {},
        )["output"]["evaluation"]
        self.assertEqual(evaluation["winner"], "c2")
        self.assertEqual(sorted(evaluation["losers"]), ["c1", "c3"])
        self.assertEqual(evaluation["next_action"], "expand_winner")


class WorkflowG1MappingTests(WorkflowTestBase):
    def test_freeform_objective_maps_to_a_valid_g1_objective(self):
        self.assertEqual(
            workflow_actions._g1_objective({"objective": "Generate qualified demo conversations"}, {}),
            "awareness",
        )
        self.assertEqual(workflow_actions._g1_objective({"objective": "trial"}, {}), "trial")
        self.assertEqual(
            workflow_actions._g1_objective({"objective": "x"}, {"g1_objective": "walkthrough"}),
            "walkthrough",
        )

    def test_g1_strategy_forwards_valid_objective_and_offline_toggle(self):
        captured = {}

        def capture(campaign_id, **kwargs):
            captured.update(kwargs)
            captured["campaign_objective"] = marketing_store.get_campaign(campaign_id)["objective"]
            return self.fake_run_g1(campaign_id)

        with patch("services.marketing_worker.run_g1", side_effect=capture):
            workflow_actions.g1_strategy(
                {"workflow_id": "wf", "objective": "Generate qualified demo conversations"},
                {"org_id": self.org["id"], "topic": "freight docs", "fresh_research": False},
            )
        self.assertFalse(captured["fresh_research"])
        self.assertEqual(captured["campaign_objective"], "awareness")

    def test_g1_strategy_stops_when_package_needs_founder_review(self):
        def not_ready(campaign_id, **kwargs):
            return {
                "campaign": {"campaign_id": "camp_x", "status": "needs_founder_review", "quality": {"warnings": []}},
                "concepts": CONCEPTS,
                "selected_concept": CONCEPTS[0],
                "package_path": "/tmp/g1.json",
            }

        with patch("services.marketing_worker.run_g1", side_effect=not_ready):
            with self.assertRaises(RuntimeError) as raised:
                workflow_actions.g1_strategy(
                    {"workflow_id": "wf", "objective": "awareness"},
                    {"org_id": self.org["id"], "topic": "t"},
                )
        self.assertIn("media gate", str(raised.exception))


class WorkflowApiTests(WorkflowTestBase):
    def client(self):
        app = FastAPI()
        app.include_router(workflows_router)
        return TestClient(app)

    def payload(self):
        return {
            "name": "InDataFlow Launch Experiment",
            "objective": "Generate qualified demo conversations",
            "trigger": {"type": "manual", "config": {"org_id": self.org["id"], "topic": "freight docs"}},
            "steps": STEPS,
            "success_metric": {"type": "conversion", "target": 0.1},
        }

    def test_create_list_inspect_run_and_state(self):
        client = self.client()
        created = client.post("/company/workflows", json=self.payload())
        self.assertEqual(created.status_code, 201)
        workflow_id = created.json()["id"]

        listed = client.get("/company/workflows").json()
        self.assertEqual([item["id"] for item in listed], [workflow_id])
        self.assertEqual(client.get(f"/company/workflows/{workflow_id}").json()["state"]["status"], "draft")

        with self.patched(self.patch_engines()):
            run = client.post(f"/company/workflows/{workflow_id}/run", json={})
        self.assertEqual(run.status_code, 200)
        self.assertEqual(run.json()["state"]["status"], "completed")

        state_payload = client.get(f"/company/workflows/{workflow_id}/state").json()
        self.assertEqual(state_payload["status"], "completed")
        self.assertEqual(len(state_payload["results"]), 5)

    def test_invalid_workflow_returns_400_without_persisting(self):
        client = self.client()
        response = client.post(
            "/company/workflows", json={"name": "Broken", "steps": [{"id": "x", "action": "nope"}]},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(client.get("/company/workflows").json(), [])

    def test_unknown_workflow_returns_404(self):
        client = self.client()
        self.assertEqual(client.get("/company/workflows/wf_missing").status_code, 404)
        self.assertEqual(client.post("/company/workflows/wf_missing/run", json={}).status_code, 404)


class WorkflowEndToEndTests(WorkflowTestBase):
    def test_full_workflow_from_objective_to_evaluation(self):
        workflow = self.make_workflow()
        sales = {"total": 5, "by_stage": {"qualified": 1, "new": 4}, "by_source": {}}
        with self.patched(self.patch_engines()), patch("core.sales_store.summary", return_value=sales):
            finished = workflow_runner.run_workflow(workflow.id)

        self.assertEqual(finished.state.status, "completed")
        self.assertEqual([item.action for item in finished.state.results], [step["action"] for step in STEPS])
        by_step = {item.step_id: item for item in finished.state.results}

        self.assertEqual(len(by_step["strategy"].output["hypotheses"]), 3)
        self.assertEqual(len(by_step["assets"].output["assets"]), 1)
        self.assertEqual(by_step["publish"].output["publications"][0]["post_id"], "buf_1")
        self.assertEqual(by_step["collect"].output["results"]["metrics"]["leads"], 5)

        evaluation = finished.state.evaluation
        self.assertIsNotNone(evaluation)
        self.assertEqual(evaluation.winner, "c2")
        self.assertEqual(sorted(evaluation.losers), ["c1", "c3"])
        self.assertEqual(evaluation.next_action, "expand_winner")
        self.assertEqual(evaluation.metrics["qualified_leads"], 1)

        campaign = marketing_store.get_campaign(by_step["strategy"].output["campaign_id"])
        self.assertEqual(campaign["status"], "drafted")
        self.assertIsNotNone(campaign["selected_variant_id"])


if __name__ == "__main__":
    unittest.main()
