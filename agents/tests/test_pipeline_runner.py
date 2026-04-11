"""
End-to-end tests for the synchronous pipeline runner.

Strategy: mock `build_chain_for_user` with a "smart" chain whose .complete()
inspects the system prompt and returns canned JSON for each agent type. This
lets us run the full 9-agent pipeline without any real provider calls.
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

from agents.models import AgentTask  # noqa: E402
from agents.orchestrator import Orchestrator  # noqa: E402
from agents.pipeline_runner import (  # noqa: E402
    MAX_BUGFIX_RETRIES,
    execute_pipeline,
)
from projects.models import FinalOutput, Pipeline, Project  # noqa: E402
from provider_settings.providers.base import ProviderResponse  # noqa: E402

User = get_user_model()


# ---------------------------------------------------------------------------
# "Smart" chain factory
# ---------------------------------------------------------------------------
def make_smart_chain(
    *,
    review_outcome: str = "approved",  # "approved" | "fixable" | "stubborn"
    fail_on: str | None = None,
):
    """
    Build a mock chain whose .complete() returns canned JSON based on the
    system prompt. Configurable knobs:
      review_outcome:
        "approved" → all reviews approve immediately
        "fixable"  → first review of each artifact rejects, then approves
                     after one bug-fix attempt
        "stubborn" → every review rejects (exercises retry exhaustion)
      fail_on: agent_type that should raise RuntimeError when invoked
    """
    state = {"reviews_per_target": {}}

    def complete(system, user, **kwargs):
        if fail_on and _detect_agent(system) == fail_on:
            raise RuntimeError(f"simulated failure for {fail_on}")

        agent = _detect_agent(system)
        body = json.loads(user)

        if agent == "research":
            content = json.dumps(
                {
                    "summary": "todo app summary",
                    "risks": ["data privacy"],
                    "ambiguities": ["mobile vs web"],
                    "best_practices": ["use OAuth"],
                }
            )
        elif agent == "pm":
            content = json.dumps(
                {
                    "user_stories": [
                        {
                            "id": "US-1",
                            "title": "Add todo",
                            "description": "As a user, I want to add a todo",
                            "acceptance_criteria": ["A1", "A2"],
                        }
                    ],
                    "scope": "MVP",
                    "out_of_scope": ["payments"],
                }
            )
        elif agent == "system_designer":
            content = json.dumps(
                {
                    "architecture_style": "modular_monolith",
                    "summary": "Django + Postgres",
                    "tech_stack": {
                        "backend": ["Django"],
                        "database": ["Postgres"],
                        "frontend": ["none"],
                        "infrastructure": ["Docker"],
                    },
                    "components": [{"name": "Todos", "responsibility": "CRUD", "interfaces": []}],
                    "key_decisions": [],
                }
            )
        elif agent == "db_schema":
            content = json.dumps(
                {
                    "models": [{"name": "Todo", "fields": [{"name": "title", "type": "char"}]}],
                    "relationships": [],
                    "indexes": [],
                    "notes": "",
                }
            )
        elif agent == "api_designer":
            content = json.dumps(
                {
                    "base_url": "/api/v1",
                    "endpoints": [{"method": "GET", "path": "/todos/"}],
                    "serializers": [],
                    "notes": "",
                }
            )
        elif agent == "code_review":
            target = body.get("target_artifact", "unknown")
            state["reviews_per_target"].setdefault(target, 0)
            state["reviews_per_target"][target] += 1
            count = state["reviews_per_target"][target]

            if review_outcome == "approved":
                approved = True
                issues = []
            elif review_outcome == "stubborn":
                approved = False
                issues = [
                    {
                        "id": f"I-{count}",
                        "severity": "major",
                        "category": "data_integrity",
                        "location": "models",
                        "problem": "still broken",
                        "suggestion": "fix it",
                    }
                ]
            elif review_outcome == "fixable":
                # First review rejects; subsequent reviews approve.
                approved = count > 1
                issues = (
                    []
                    if approved
                    else [
                        {
                            "id": "I-1",
                            "severity": "major",
                            "category": "data_integrity",
                            "location": "models",
                            "problem": "missing index",
                            "suggestion": "add index",
                        }
                    ]
                )
            else:
                raise ValueError(f"unknown review_outcome: {review_outcome!r}")

            content = json.dumps(
                {
                    "approved": approved,
                    "summary": "ok" if approved else "needs fixes",
                    "issues": issues,
                }
            )
        elif agent == "bug_fixer":
            target = body.get("target_artifact", "unknown")
            content = json.dumps(
                {
                    "revised_artifact": {
                        "models": [{"name": "FixedTodo"}],
                        "relationships": [],
                        "indexes": [{"model": "FixedTodo", "fields": ["title"], "rationale": "added"}],
                    },
                    "applied_fixes": [{"issue_id": "I-1", "change": "added index"}],
                    "unaddressed_issues": [],
                }
            )
        elif agent == "testing":
            content = json.dumps(
                {
                    "unit_tests": [
                        {
                            "id": "UT-1",
                            "target": "Todo",
                            "name": "test_create",
                            "description": "create a todo",
                            "type": "happy_path",
                            "setup": "none",
                            "assertions": ["created"],
                        }
                    ],
                    "integration_tests": [],
                    "coverage_notes": "ok",
                }
            )
        elif agent == "documentation":
            content = json.dumps(
                {
                    "title": "Project Design Document",
                    "report_markdown": "# Overview\n\nThis is the report.",
                    "table_of_contents": ["1. Overview"],
                }
            )
        else:
            raise ValueError(f"unknown agent: {agent!r}")

        return (
            ProviderResponse(content=content, provider="groq", model="m", tokens_used=10),
            "groq",
        )

    chain = MagicMock()
    chain.complete.side_effect = complete
    return chain


def _detect_agent(system_prompt: str) -> str:
    """Crude inversion of the prompt files — used by the mock chain."""
    if "Research Analyst" in system_prompt:
        return "research"
    if "Product Manager" in system_prompt:
        return "pm"
    if "Solution Architect" in system_prompt:
        return "system_designer"
    if "Database Engineer" in system_prompt:
        return "db_schema"
    if "API Architect" in system_prompt:
        return "api_designer"
    if "Code Reviewer" in system_prompt:
        return "code_review"
    if "Bug Fixer" in system_prompt:
        return "bug_fixer"
    if "QA Engineer" in system_prompt:
        return "testing"
    if "Technical Writer" in system_prompt:
        return "documentation"
    raise ValueError(f"could not detect agent from system prompt: {system_prompt[:80]!r}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_pipeline(user) -> Pipeline:
    project = Project.objects.create(requirement="Build a todo app", created_by=user)
    return Orchestrator.initialize_pipeline(project)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------
class HappyPathTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("happy", password="pw")
        self.pipeline = _make_pipeline(self.user)

    def test_pipeline_completes_successfully(self):
        with patch("agents.runner.build_chain_for_user", return_value=make_smart_chain()):
            execute_pipeline(self.pipeline.pk)

        self.pipeline.project.refresh_from_db()
        self.assertEqual(self.pipeline.project.status, Project.STATUS_COMPLETED)

    def test_pipeline_records_started_and_finished_times(self):
        with patch("agents.runner.build_chain_for_user", return_value=make_smart_chain()):
            execute_pipeline(self.pipeline.pk)

        self.pipeline.refresh_from_db()
        self.assertIsNotNone(self.pipeline.started_at)
        self.assertIsNotNone(self.pipeline.finished_at)
        self.assertGreaterEqual(self.pipeline.finished_at, self.pipeline.started_at)

    def test_all_9_agent_tasks_created(self):
        with patch("agents.runner.build_chain_for_user", return_value=make_smart_chain()):
            execute_pipeline(self.pipeline.pk)

        # 9 distinct steps (code_review appears twice → 9 AgentTasks total
        # because code_review-db and code_review-api share the agent_type
        # but are separate rows distinguishable by target_artifact).
        tasks = AgentTask.objects.filter(pipeline=self.pipeline)
        self.assertEqual(tasks.count(), 9)

    def test_all_agent_tasks_done(self):
        with patch("agents.runner.build_chain_for_user", return_value=make_smart_chain()):
            execute_pipeline(self.pipeline.pk)

        tasks = AgentTask.objects.filter(pipeline=self.pipeline)
        for task in tasks:
            self.assertEqual(task.status, AgentTask.STATUS_DONE, f"{task} not done")

    def test_creates_final_output(self):
        with patch("agents.runner.build_chain_for_user", return_value=make_smart_chain()):
            execute_pipeline(self.pipeline.pk)

        final = FinalOutput.objects.get(project=self.pipeline.project)
        self.assertIn("# Overview", final.full_report)
        self.assertIn("research", final.per_agent_outputs)
        self.assertIn("documentation", final.per_agent_outputs)


# ---------------------------------------------------------------------------
# Bug-fix loop
# ---------------------------------------------------------------------------
class BugFixLoopTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("bugfix_user", password="pw")
        self.pipeline = _make_pipeline(self.user)

    def test_no_bugfixer_called_when_review_approved(self):
        with patch("agents.runner.build_chain_for_user", return_value=make_smart_chain(review_outcome="approved")):
            execute_pipeline(self.pipeline.pk)

        bugfix_count = AgentTask.objects.filter(
            pipeline=self.pipeline, agent_type="bug_fixer"
        ).count()
        self.assertEqual(bugfix_count, 0)

    def test_bugfixer_called_once_when_review_then_passes(self):
        """One rejection per artifact → one bug_fixer + one re-review per target."""
        with patch("agents.runner.build_chain_for_user", return_value=make_smart_chain(review_outcome="fixable")):
            execute_pipeline(self.pipeline.pk)

        # Two artifacts (db_schema, api_designer) each get one bug fix.
        bugfix_count = AgentTask.objects.filter(
            pipeline=self.pipeline, agent_type="bug_fixer"
        ).count()
        self.assertEqual(bugfix_count, 2)

    def test_bugfixer_replaces_artifact_in_snapshot(self):
        with patch("agents.runner.build_chain_for_user", return_value=make_smart_chain(review_outcome="fixable")):
            execute_pipeline(self.pipeline.pk)

        self.pipeline.refresh_from_db()
        outputs = self.pipeline.context_snapshot["outputs"]
        # The db_schema in the final snapshot should be the *revised* one
        # produced by the bug fixer (which contains a model named "FixedTodo").
        models = outputs["db_schema"]["models"]
        self.assertEqual(models[0]["name"], "FixedTodo")

    def test_stubborn_review_exhausts_retries_but_pipeline_completes(self):
        """If review never approves, we log a warning and proceed."""
        with patch("agents.runner.build_chain_for_user", return_value=make_smart_chain(review_outcome="stubborn")):
            execute_pipeline(self.pipeline.pk)

        # Pipeline still completes successfully.
        self.pipeline.project.refresh_from_db()
        self.assertEqual(self.pipeline.project.status, Project.STATUS_COMPLETED)

        # MAX_BUGFIX_RETRIES bug_fixer attempts per artifact.
        bugfix_count = AgentTask.objects.filter(
            pipeline=self.pipeline, agent_type="bug_fixer"
        ).count()
        self.assertEqual(bugfix_count, MAX_BUGFIX_RETRIES * 2)  # 2 artifacts


# ---------------------------------------------------------------------------
# Failure path
# ---------------------------------------------------------------------------
class FailurePathTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("fail_user", password="pw")
        self.pipeline = _make_pipeline(self.user)

    def test_pipeline_fails_when_agent_raises(self):
        with patch(
            "agents.runner.build_chain_for_user",
            return_value=make_smart_chain(fail_on="db_schema"),
        ):
            with self.assertRaises(RuntimeError):
                execute_pipeline(self.pipeline.pk)

        self.pipeline.project.refresh_from_db()
        self.assertEqual(self.pipeline.project.status, Project.STATUS_FAILED)

    def test_failed_pipeline_records_finished_at(self):
        with patch(
            "agents.runner.build_chain_for_user",
            return_value=make_smart_chain(fail_on="research"),
        ):
            with self.assertRaises(RuntimeError):
                execute_pipeline(self.pipeline.pk)

        self.pipeline.refresh_from_db()
        self.assertIsNotNone(self.pipeline.finished_at)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
