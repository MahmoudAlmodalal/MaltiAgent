"""
Unit tests for BaseAgent.

Uses a tiny concrete subclass `_DummyResearchAgent` and a MagicMock provider
chain so no real provider calls are made. The DB is set up via SQLite in-memory.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_test")

import django  # noqa: E402

django.setup()

from django.core.management import call_command  # noqa: E402

call_command("migrate", "--run-syncdb", verbosity=0)

from django.test import TestCase  # noqa: E402

from agents.base_agent import BaseAgent  # noqa: E402
from agents.context_manager import ContextManager  # noqa: E402
from agents.models import AgentTask  # noqa: E402
from projects.models import Pipeline, Project  # noqa: E402
from provider_settings.providers.base import ProviderResponse  # noqa: E402


# ---------------------------------------------------------------------------
# Concrete subclass for testing
# ---------------------------------------------------------------------------
class _DummyResearchAgent(BaseAgent):
    agent_type = "research"

    def _build_user_message(self, slice_data: dict) -> str:
        return json.dumps(slice_data)


def _mock_chain(content: str = '{"summary": "ok", "risks": [], "ambiguities": [], "best_practices": []}',
                provider: str = "groq", tokens: int = 50):
    chain = MagicMock()
    response = ProviderResponse(
        content=content, provider=provider, model="test-model", tokens_used=tokens
    )
    chain.complete.return_value = (response, provider)
    return chain


def _make_pipeline(requirement="Build a todo app"):
    project = Project.objects.create(requirement=requirement)
    return Pipeline.objects.create(
        project=project,
        context_snapshot={"requirement": requirement, "outputs": {}},
    )


# ---------------------------------------------------------------------------
# Run / persistence tests
# ---------------------------------------------------------------------------
class BaseAgentRunTests(TestCase):
    def test_run_creates_agent_task_with_done_status(self):
        pipeline = _make_pipeline()
        ctx = ContextManager(snapshot=pipeline.context_snapshot)
        agent = _DummyResearchAgent(pipeline, ctx, _mock_chain())

        agent.run()

        task = AgentTask.objects.get(pipeline=pipeline, agent_type="research")
        self.assertEqual(task.status, AgentTask.STATUS_DONE)

    def test_run_records_provider_used(self):
        pipeline = _make_pipeline()
        ctx = ContextManager(snapshot=pipeline.context_snapshot)
        agent = _DummyResearchAgent(pipeline, ctx, _mock_chain(provider="ollama"))

        agent.run()

        task = AgentTask.objects.get(pipeline=pipeline, agent_type="research")
        self.assertEqual(task.provider_used, "ollama")

    def test_run_records_duration_ms(self):
        pipeline = _make_pipeline()
        ctx = ContextManager(snapshot=pipeline.context_snapshot)
        agent = _DummyResearchAgent(pipeline, ctx, _mock_chain())

        agent.run()

        task = AgentTask.objects.get(pipeline=pipeline, agent_type="research")
        self.assertGreaterEqual(task.duration_ms, 0)

    def test_run_persists_input_slice(self):
        pipeline = _make_pipeline("Build a chat app")
        ctx = ContextManager(snapshot=pipeline.context_snapshot)
        agent = _DummyResearchAgent(pipeline, ctx, _mock_chain())

        agent.run()

        task = AgentTask.objects.get(pipeline=pipeline, agent_type="research")
        self.assertEqual(task.input_slice["requirement"], "Build a chat app")

    def test_run_saves_output_to_context_manager(self):
        pipeline = _make_pipeline()
        ctx = ContextManager(snapshot=pipeline.context_snapshot)
        agent = _DummyResearchAgent(
            pipeline,
            ctx,
            _mock_chain(content='{"summary": "test summary", "risks": ["r1"], "ambiguities": [], "best_practices": []}'),
        )

        agent.run()

        research = ctx.output_for("research")
        self.assertEqual(research["summary"], "test summary")
        self.assertEqual(research["risks"], ["r1"])

    def test_run_returns_parsed_output(self):
        pipeline = _make_pipeline()
        ctx = ContextManager(snapshot=pipeline.context_snapshot)
        agent = _DummyResearchAgent(
            pipeline,
            ctx,
            _mock_chain(content='{"summary": "S", "risks": [], "ambiguities": [], "best_practices": []}'),
        )

        result = agent.run()

        self.assertEqual(result["summary"], "S")

    def test_run_strips_markdown_code_fence(self):
        pipeline = _make_pipeline()
        ctx = ContextManager(snapshot=pipeline.context_snapshot)
        fenced = '```json\n{"summary": "fenced", "risks": [], "ambiguities": [], "best_practices": []}\n```'
        agent = _DummyResearchAgent(pipeline, ctx, _mock_chain(content=fenced))

        result = agent.run()

        self.assertEqual(result["summary"], "fenced")


# ---------------------------------------------------------------------------
# Failure path
# ---------------------------------------------------------------------------
class BaseAgentFailureTests(TestCase):
    def test_run_marks_task_failed_on_provider_exception(self):
        pipeline = _make_pipeline()
        ctx = ContextManager(snapshot=pipeline.context_snapshot)
        chain = MagicMock()
        chain.complete.side_effect = RuntimeError("provider down")
        agent = _DummyResearchAgent(pipeline, ctx, chain)

        with self.assertRaises(RuntimeError):
            agent.run()

        task = AgentTask.objects.get(pipeline=pipeline, agent_type="research")
        self.assertEqual(task.status, AgentTask.STATUS_FAILED)
        self.assertIn("provider down", task.error)

    def test_run_does_not_save_output_on_failure(self):
        pipeline = _make_pipeline()
        ctx = ContextManager(snapshot=pipeline.context_snapshot)
        chain = MagicMock()
        chain.complete.side_effect = RuntimeError("boom")
        agent = _DummyResearchAgent(pipeline, ctx, chain)

        with self.assertRaises(RuntimeError):
            agent.run()

        # ContextManager should not have a research output.
        self.assertIsNone(ctx.output_for("research"))

    def test_run_marks_task_failed_on_invalid_json(self):
        pipeline = _make_pipeline()
        ctx = ContextManager(snapshot=pipeline.context_snapshot)
        agent = _DummyResearchAgent(
            pipeline, ctx, _mock_chain(content="this is not json at all")
        )

        with self.assertRaises(json.JSONDecodeError):
            agent.run()

        task = AgentTask.objects.get(pipeline=pipeline, agent_type="research")
        self.assertEqual(task.status, AgentTask.STATUS_FAILED)


# ---------------------------------------------------------------------------
# Helpers (no DB)
# ---------------------------------------------------------------------------
class ExtractJSONTests(unittest.TestCase):
    def test_plain_json(self):
        self.assertEqual(BaseAgent._extract_json('{"a": 1}'), {"a": 1})

    def test_strips_json_fence(self):
        text = '```json\n{"a": 1}\n```'
        self.assertEqual(BaseAgent._extract_json(text), {"a": 1})

    def test_strips_plain_fence(self):
        text = '```\n{"a": 1}\n```'
        self.assertEqual(BaseAgent._extract_json(text), {"a": 1})

    def test_extracts_json_from_prose(self):
        text = 'Sure thing! Here is the JSON: {"a": 1, "b": [2, 3]} cheers'
        self.assertEqual(BaseAgent._extract_json(text), {"a": 1, "b": [2, 3]})

    def test_raises_on_no_json(self):
        with self.assertRaises(json.JSONDecodeError):
            BaseAgent._extract_json("just some text, no json here")


class LoadSystemPromptTests(unittest.TestCase):
    def test_loads_real_prompt_file(self):
        agent = _DummyResearchAgent.__new__(_DummyResearchAgent)
        agent.agent_type = "research"
        prompt = agent._load_system_prompt()
        self.assertIn("Research Analyst", prompt)

    def test_raises_for_missing_prompt(self):
        class _MissingAgent(BaseAgent):
            agent_type = "totally_not_a_real_agent"

            def _build_user_message(self, slice_data):
                return ""

        agent = _MissingAgent.__new__(_MissingAgent)
        agent.agent_type = "totally_not_a_real_agent"
        with self.assertRaises(FileNotFoundError):
            agent._load_system_prompt()


class SubclassValidationTests(unittest.TestCase):
    def test_subclass_without_agent_type_raises(self):
        class _NoTypeAgent(BaseAgent):
            agent_type = ""  # explicitly empty

            def _build_user_message(self, slice_data):
                return ""

        with self.assertRaises(NotImplementedError):
            _NoTypeAgent(MagicMock(), MagicMock(), MagicMock())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
