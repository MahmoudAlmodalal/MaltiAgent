"""
Unit tests for agents.runner.run_agent — the integration helper that loads
Pipeline state, builds the provider chain, runs an agent, and persists the
updated context snapshot.
"""
import json
import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_test")

import django  # noqa: E402

django.setup()

from django.core.management import call_command  # noqa: E402

call_command("migrate", "--run-syncdb", verbosity=0)

from django.contrib.auth import get_user_model  # noqa: E402
from django.test import TestCase  # noqa: E402

from agents.base_agent import BaseAgent  # noqa: E402
from agents.models import AgentTask  # noqa: E402
from agents.runner import run_agent  # noqa: E402
from projects.models import Pipeline, Project  # noqa: E402
from provider_settings.providers.base import ProviderResponse  # noqa: E402

User = get_user_model()


# ---------------------------------------------------------------------------
# Concrete subclass for testing
# ---------------------------------------------------------------------------
class _RunnerTestAgent(BaseAgent):
    agent_type = "research"

    def _build_user_message(self, slice_data: dict) -> str:
        return json.dumps(slice_data)


def _ok_chain(content='{"summary": "x", "risks": [], "ambiguities": [], "best_practices": []}'):
    chain = MagicMock()
    chain.complete.return_value = (
        ProviderResponse(content=content, provider="groq", model="m", tokens_used=10),
        "groq",
    )
    return chain


class RunAgentTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("runner_test", password="pw")
        self.project = Project.objects.create(
            requirement="Build a todo app", created_by=self.user
        )
        self.pipeline = Pipeline.objects.create(
            project=self.project,
            context_snapshot={
                "requirement": "Build a todo app",
                "outputs": {},
            },
        )

    def test_runs_agent_and_returns_output(self):
        with patch("agents.runner.build_chain_for_user", return_value=_ok_chain()):
            output = run_agent(self.pipeline.pk, _RunnerTestAgent)

        self.assertEqual(output["summary"], "x")

    def test_persists_updated_context_snapshot(self):
        with patch("agents.runner.build_chain_for_user", return_value=_ok_chain()):
            run_agent(self.pipeline.pk, _RunnerTestAgent)

        self.pipeline.refresh_from_db()
        outputs = self.pipeline.context_snapshot["outputs"]
        self.assertIn("research", outputs)
        self.assertEqual(outputs["research"]["summary"], "x")

    def test_advances_current_step(self):
        with patch("agents.runner.build_chain_for_user", return_value=_ok_chain()):
            run_agent(self.pipeline.pk, _RunnerTestAgent)

        self.pipeline.refresh_from_db()
        self.assertEqual(self.pipeline.current_step, "research")

    def test_creates_agent_task_record(self):
        with patch("agents.runner.build_chain_for_user", return_value=_ok_chain()):
            run_agent(self.pipeline.pk, _RunnerTestAgent)

        task = AgentTask.objects.get(pipeline=self.pipeline, agent_type="research")
        self.assertEqual(task.status, AgentTask.STATUS_DONE)

    def test_provider_failure_marks_task_failed_and_does_not_advance(self):
        broken_chain = MagicMock()
        broken_chain.complete.side_effect = RuntimeError("network down")

        with patch("agents.runner.build_chain_for_user", return_value=broken_chain):
            with self.assertRaises(RuntimeError):
                run_agent(self.pipeline.pk, _RunnerTestAgent)

        # Pipeline.current_step should NOT have advanced.
        self.pipeline.refresh_from_db()
        self.assertEqual(self.pipeline.current_step, "")
        # AgentTask should be marked failed.
        task = AgentTask.objects.get(pipeline=self.pipeline, agent_type="research")
        self.assertEqual(task.status, AgentTask.STATUS_FAILED)
        self.assertIn("network down", task.error)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
