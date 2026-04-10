"""
Tests for the 9 concrete agent implementations.

Each agent is verified to:
- declare the right `agent_type`
- be registered in AGENT_CLASSES
- format the user message correctly (valid JSON)
- run end-to-end through BaseAgent.run() with a mocked provider chain
"""
import json
import os
import unittest
from unittest.mock import MagicMock

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_test")

import django  # noqa: E402

django.setup()

from django.core.management import call_command  # noqa: E402

call_command("migrate", "--run-syncdb", verbosity=0)

from django.test import TestCase  # noqa: E402

from agents.base_agent import BaseAgent  # noqa: E402
from agents.context_manager import ALL_AGENTS, ContextManager  # noqa: E402
from agents.implementations import (  # noqa: E402
    AGENT_CLASSES,
    APIDesignerAgent,
    BugFixerAgent,
    CodeReviewAgent,
    DBSchemaAgent,
    DocumentationAgent,
    PMAgent,
    ResearchAgent,
    SystemDesignerAgent,
    TestingAgent,
)
from agents.models import AgentTask  # noqa: E402
from projects.models import Pipeline, Project  # noqa: E402
from provider_settings.providers.base import ProviderResponse  # noqa: E402


def _mock_chain(content: str):
    chain = MagicMock()
    chain.complete.return_value = (
        ProviderResponse(content=content, provider="groq", model="m", tokens_used=10),
        "groq",
    )
    return chain


def _make_pipeline(snapshot: dict | None = None) -> Pipeline:
    project = Project.objects.create(requirement="Build a todo app")
    return Pipeline.objects.create(
        project=project,
        context_snapshot=snapshot
        or {"requirement": "Build a todo app", "outputs": {}},
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
class AgentRegistryTests(unittest.TestCase):
    def test_all_9_agent_types_have_implementations(self):
        for agent_type in ALL_AGENTS:
            self.assertIn(
                agent_type, AGENT_CLASSES, f"missing implementation for {agent_type!r}"
            )

    def test_no_extra_agents_in_registry(self):
        self.assertEqual(set(AGENT_CLASSES.keys()), set(ALL_AGENTS))

    def test_each_agent_class_subclasses_base_agent(self):
        for cls in AGENT_CLASSES.values():
            self.assertTrue(issubclass(cls, BaseAgent))

    def test_agent_type_matches_registry_key(self):
        for key, cls in AGENT_CLASSES.items():
            self.assertEqual(cls.agent_type, key)


# ---------------------------------------------------------------------------
# User-message formatting
# ---------------------------------------------------------------------------
class UserMessageFormatTests(unittest.TestCase):
    """Each agent's _build_user_message must produce valid JSON."""

    def _instance(self, cls):
        return cls.__new__(cls)

    def test_research_user_message_is_valid_json(self):
        agent = self._instance(ResearchAgent)
        slice_data = {"requirement": "build x"}
        msg = agent._build_user_message(slice_data)
        self.assertEqual(json.loads(msg), slice_data)

    def test_pm_user_message_is_valid_json(self):
        agent = self._instance(PMAgent)
        slice_data = {"requirement": "x", "research": {"summary": "s", "risks": []}}
        msg = agent._build_user_message(slice_data)
        self.assertEqual(json.loads(msg), slice_data)

    def test_system_designer_user_message_is_valid_json(self):
        agent = self._instance(SystemDesignerAgent)
        slice_data = {"requirement": "x", "user_stories": [], "scope": "s", "risks": []}
        msg = agent._build_user_message(slice_data)
        self.assertEqual(json.loads(msg), slice_data)

    def test_db_schema_user_message_is_valid_json(self):
        agent = self._instance(DBSchemaAgent)
        slice_data = {"requirement": "x", "architecture": {"components": []}}
        msg = agent._build_user_message(slice_data)
        self.assertEqual(json.loads(msg), slice_data)

    def test_api_designer_user_message_is_valid_json(self):
        agent = self._instance(APIDesignerAgent)
        slice_data = {"requirement": "x", "db_schema": {"models": []}}
        msg = agent._build_user_message(slice_data)
        self.assertEqual(json.loads(msg), slice_data)

    def test_code_review_user_message_is_valid_json(self):
        agent = self._instance(CodeReviewAgent)
        slice_data = {
            "requirement": "x",
            "target_artifact": "db_schema",
            "artifact": {"models": []},
        }
        msg = agent._build_user_message(slice_data)
        self.assertEqual(json.loads(msg), slice_data)

    def test_bug_fixer_user_message_is_valid_json(self):
        agent = self._instance(BugFixerAgent)
        slice_data = {
            "requirement": "x",
            "target_artifact": "db_schema",
            "artifact": {"models": []},
            "latest_review": {"issues": []},
        }
        msg = agent._build_user_message(slice_data)
        self.assertEqual(json.loads(msg), slice_data)

    def test_testing_user_message_is_valid_json(self):
        agent = self._instance(TestingAgent)
        slice_data = {
            "requirement": "x",
            "db_schema": {"models": []},
            "api_design": {"endpoints": []},
        }
        msg = agent._build_user_message(slice_data)
        self.assertEqual(json.loads(msg), slice_data)

    def test_documentation_user_message_is_valid_json(self):
        agent = self._instance(DocumentationAgent)
        slice_data = {
            "requirement": "x",
            "all_outputs": {"research": {"summary": "s"}},
        }
        msg = agent._build_user_message(slice_data)
        self.assertEqual(json.loads(msg), slice_data)


# ---------------------------------------------------------------------------
# End-to-end run with mocked providers
# ---------------------------------------------------------------------------
class EndToEndAgentRunTests(TestCase):
    """Each agent runs through BaseAgent.run() and persists an AgentTask."""

    def _seed_full_context(self) -> ContextManager:
        """Seed every upstream output so any agent can run."""
        ctx = ContextManager(requirement="Build a todo app")
        ctx.save_output(
            "research",
            {
                "summary": "todo app for couples",
                "risks": ["data privacy"],
                "ambiguities": ["mobile vs web?"],
                "best_practices": ["use OAuth"],
            },
        )
        ctx.save_output(
            "pm",
            {
                "user_stories": [
                    {
                        "id": "US-1",
                        "title": "Add todo",
                        "description": "As a user, I want to add a todo",
                        "acceptance_criteria": ["form submits", "todo appears"],
                    }
                ],
                "scope": "MVP for couples",
                "out_of_scope": ["payments"],
            },
        )
        ctx.save_output(
            "system_designer",
            {
                "architecture_style": "modular_monolith",
                "summary": "Django + Postgres",
                "tech_stack": {"backend": ["Django"], "database": ["Postgres"]},
                "components": [{"name": "Todos", "responsibility": "CRUD"}],
            },
        )
        ctx.save_output(
            "db_schema",
            {
                "models": [{"name": "Todo", "fields": [{"name": "title", "type": "char"}]}],
                "relationships": [],
                "indexes": [],
            },
        )
        ctx.save_output(
            "api_designer",
            {
                "base_url": "/api/v1",
                "endpoints": [{"method": "GET", "path": "/todos/"}],
                "serializers": [],
            },
        )
        return ctx

    def test_research_agent_runs(self):
        pipeline = _make_pipeline()
        ctx = ContextManager(snapshot=pipeline.context_snapshot)
        agent = ResearchAgent(
            pipeline,
            ctx,
            _mock_chain('{"summary": "ok", "risks": [], "ambiguities": [], "best_practices": []}'),
        )
        result = agent.run()
        self.assertIn("summary", result)
        self.assertEqual(
            AgentTask.objects.get(pipeline=pipeline, agent_type="research").status,
            AgentTask.STATUS_DONE,
        )

    def test_pm_agent_runs_after_research(self):
        pipeline = _make_pipeline()
        ctx = self._seed_full_context()
        agent = PMAgent(
            pipeline,
            ctx,
            _mock_chain('{"user_stories": [], "scope": "s", "out_of_scope": []}'),
        )
        agent.run()
        self.assertEqual(
            AgentTask.objects.get(pipeline=pipeline, agent_type="pm").status,
            AgentTask.STATUS_DONE,
        )

    def test_db_schema_agent_runs(self):
        pipeline = _make_pipeline()
        ctx = self._seed_full_context()
        agent = DBSchemaAgent(
            pipeline,
            ctx,
            _mock_chain('{"models": [], "relationships": [], "indexes": []}'),
        )
        agent.run()
        self.assertEqual(
            AgentTask.objects.get(pipeline=pipeline, agent_type="db_schema").status,
            AgentTask.STATUS_DONE,
        )

    def test_code_review_agent_runs_with_target_artifact(self):
        pipeline = _make_pipeline()
        ctx = self._seed_full_context()
        agent = CodeReviewAgent(
            pipeline,
            ctx,
            _mock_chain('{"approved": true, "summary": "looks good", "issues": []}'),
        )
        agent.run(target_artifact="db_schema")
        task = AgentTask.objects.get(pipeline=pipeline, agent_type="code_review")
        self.assertEqual(task.status, AgentTask.STATUS_DONE)
        self.assertEqual(task.target_artifact, "db_schema")

    def test_bug_fixer_agent_runs_with_review(self):
        pipeline = _make_pipeline()
        ctx = self._seed_full_context()
        ctx.save_output(
            "code_review",
            {
                "target_artifact": "db_schema",
                "approved": False,
                "issues": [{"id": "I-1", "problem": "missing index"}],
            },
        )
        agent = BugFixerAgent(
            pipeline,
            ctx,
            _mock_chain('{"revised_artifact": {"models": []}, "applied_fixes": [], "unaddressed_issues": []}'),
        )
        agent.run(target_artifact="db_schema")
        task = AgentTask.objects.get(pipeline=pipeline, agent_type="bug_fixer")
        self.assertEqual(task.status, AgentTask.STATUS_DONE)

    def test_documentation_agent_sees_all_outputs(self):
        pipeline = _make_pipeline()
        ctx = self._seed_full_context()
        ctx.save_output(
            "testing",
            {"unit_tests": [], "integration_tests": [], "coverage_notes": ""},
        )

        captured_user_message = {}

        def fake_complete(system, user, **kwargs):
            captured_user_message["msg"] = user
            return (
                ProviderResponse(
                    content='{"title": "Doc", "report_markdown": "# Hi", "table_of_contents": []}',
                    provider="groq",
                    model="m",
                ),
                "groq",
            )

        chain = MagicMock()
        chain.complete.side_effect = fake_complete

        agent = DocumentationAgent(pipeline, ctx, chain)
        agent.run()

        # The user message should contain all upstream outputs.
        body = json.loads(captured_user_message["msg"])
        self.assertIn("all_outputs", body)
        self.assertIn("research", body["all_outputs"])
        self.assertIn("pm", body["all_outputs"])
        self.assertIn("db_schema", body["all_outputs"])
        self.assertIn("api_designer", body["all_outputs"])
        self.assertIn("testing", body["all_outputs"])


# ---------------------------------------------------------------------------
# Per-agent custom config (temperature, max_tokens overrides)
# ---------------------------------------------------------------------------
class AgentTuningTests(unittest.TestCase):
    def test_research_uses_higher_temperature_for_creativity(self):
        self.assertGreater(ResearchAgent.DEFAULT_TEMPERATURE, 0.2)

    def test_code_review_uses_zero_temperature_for_determinism(self):
        self.assertEqual(CodeReviewAgent.DEFAULT_TEMPERATURE, 0.0)

    def test_db_schema_has_larger_max_tokens(self):
        self.assertGreater(DBSchemaAgent.DEFAULT_MAX_TOKENS, BaseAgent.DEFAULT_MAX_TOKENS)

    def test_documentation_has_largest_max_tokens(self):
        self.assertGreaterEqual(
            DocumentationAgent.DEFAULT_MAX_TOKENS, DBSchemaAgent.DEFAULT_MAX_TOKENS
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
