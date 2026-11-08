"""Workflow layer tests after the campaign/media lanes were removed.

The runner and API are exercised against a temporary database. Individual
actions are substituted at the ``services.workflow_actions`` boundary; the
workflow architecture itself is never faked.
"""

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
    {"id": "simulate", "action": "simulate_outreach"},
    {"id": "draft", "action": "draft_outreach"},
    {"id": "research", "action": "research_prospects"},
    {"id": "send", "action": "send_outreach"},
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

    def patched(self, patcher_list):
        stack = ExitStack()
        for patcher in patcher_list:
            stack.enter_context(patcher)
        return stack


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


class WorkflowModelTests(WorkflowTestBase):
    def test_valid_workflow_is_created_ready_to_run(self):
        workflow = self.make_workflow()
        self.assertTrue(workflow.id.startswith("wf_"))
        self.assertEqual(workflow.state.status, "draft")
        self.assertEqual([step.action for step in workflow.steps], [
            "simulate_outreach", "draft_outreach", "research_prospects", "send_outreach",
        ])
        self.assertEqual(workflow_runner.validate_workflow(workflow), [])

    def test_removed_campaign_actions_are_unknown(self):
        workflow = self.make_workflow(steps=[
            {"id": "a", "action": "g1_strategy"},
            {"id": "a", "action": "send_outreach"},
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
        self.assertEqual(len(reloaded.steps), 4)


class WorkflowRunnerTests(WorkflowTestBase):
    def test_steps_execute_in_order_and_state_is_persisted(self):
        calls = []
        workflow = self.make_workflow()
        with self.patched(patchers(stub_actions(calls))):
            finished = workflow_runner.run_workflow(workflow.id)
        self.assertEqual(calls, ["simulate_outreach", "draft_outreach", "research_prospects", "send_outreach"])
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
            raise RuntimeError("draft exploded")

        workflow = self.make_workflow()
        with self.patched(patchers(stub_actions(calls, {"draft_outreach": boom}))):
            finished = workflow_runner.run_workflow(workflow.id)
        self.assertEqual(finished.state.status, "failed")
        self.assertIn("draft exploded", finished.state.error or "")
        self.assertEqual(calls, ["simulate_outreach", "draft_outreach"])
        failed = [item for item in finished.state.results if item.step_id == "draft"]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0].status, "failed")

    def test_resume_does_not_repeat_completed_steps(self):
        calls = []
        attempts = {"draft": 0}

        def flaky_draft(context, config):
            attempts["draft"] += 1
            if attempts["draft"] == 1:
                raise RuntimeError("transient")
            return {"status": "completed", "output": {}}

        workflow = self.make_workflow()
        with self.patched(patchers(stub_actions(calls, {"draft_outreach": flaky_draft}))):
            failed = workflow_runner.run_workflow(workflow.id)
            self.assertEqual(failed.state.status, "failed")
            resumed = workflow_runner.run_workflow(workflow.id, resume=True)
        self.assertEqual(resumed.state.status, "completed")
        self.assertEqual(calls.count("simulate_outreach"), 1)
        self.assertEqual(calls.count("draft_outreach"), 2)
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


class WorkflowApiTests(WorkflowTestBase):
    def client(self):
        app = FastAPI()
        app.include_router(workflows_router)
        return TestClient(app)

    def setUp(self):
        super().setUp()
        import os
        self._env = patch.dict(os.environ, {"SALES_ACTION_TOKEN": "action-secret"}, clear=False)
        self._env.start()
        self.headers = {"X-Founder-Action-Token": "action-secret"}

    def tearDown(self):
        self._env.stop()
        super().tearDown()

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
        created = client.post("/company/workflows", json=self.payload(), headers=self.headers)
        self.assertEqual(created.status_code, 201)
        workflow_id = created.json()["id"]

        listed = client.get("/company/workflows").json()
        self.assertEqual([item["id"] for item in listed], [workflow_id])
        self.assertEqual(client.get(f"/company/workflows/{workflow_id}").json()["state"]["status"], "draft")

        with self.patched(patchers(stub_actions([]))):
            run = client.post(f"/company/workflows/{workflow_id}/run", json={}, headers=self.headers)
        self.assertEqual(run.status_code, 200)
        self.assertEqual(run.json()["state"]["status"], "completed")

        state_payload = client.get(f"/company/workflows/{workflow_id}/state").json()
        self.assertEqual(state_payload["status"], "completed")
        self.assertEqual(len(state_payload["results"]), 4)

    def test_invalid_workflow_returns_400_without_persisting(self):
        client = self.client()
        response = client.post(
            "/company/workflows", json={"name": "Broken", "steps": [{"id": "x", "action": "nope"}]},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(client.get("/company/workflows").json(), [])

    def test_unknown_workflow_returns_404(self):
        client = self.client()
        self.assertEqual(client.get("/company/workflows/wf_missing").status_code, 404)
        self.assertEqual(client.post("/company/workflows/wf_missing/run", json={}, headers=self.headers).status_code, 404)

    def test_mutations_require_the_founder_token(self):
        client = self.client()
        self.assertEqual(client.post("/company/workflows", json=self.payload()).status_code, 403)
        self.assertEqual(client.get("/company/workflows").status_code, 200)
