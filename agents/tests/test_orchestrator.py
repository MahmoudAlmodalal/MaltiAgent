"""
Unit tests for the Orchestrator.
"""
import os
import unittest

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_test")

import django  # noqa: E402

django.setup()

from django.core.management import call_command  # noqa: E402

call_command("migrate", "--run-syncdb", verbosity=0)

from django.test import TestCase  # noqa: E402

from agents.orchestrator import Orchestrator  # noqa: E402
from projects.models import Pipeline, Project  # noqa: E402


class BuildExecutionPlanTests(unittest.TestCase):
    def test_returns_versioned_plan(self):
        plan = Orchestrator.build_execution_plan("Build a todo app")
        self.assertEqual(plan["version"], Orchestrator.PLAN_VERSION)
        self.assertIn("steps", plan)

    def test_plan_has_nine_steps(self):
        # 9 distinct steps: research, pm, system_designer, db_schema, review_db,
        # api_designer, review_api, testing, documentation. (code_review appears
        # twice but bug_fixer is excluded.)
        plan = Orchestrator.build_execution_plan("x")
        self.assertEqual(len(plan["steps"]), 9)

    def test_dependencies_are_topologically_valid(self):
        plan = Orchestrator.build_execution_plan("x")
        seen_ids: set[str] = set()
        for step in plan["steps"]:
            for dep in step["depends_on"]:
                self.assertIn(
                    dep, seen_ids, f"step {step['id']!r} depends on unseen {dep!r}"
                )
            seen_ids.add(step["id"])

    def test_first_step_is_research_with_no_deps(self):
        plan = Orchestrator.build_execution_plan("x")
        first = plan["steps"][0]
        self.assertEqual(first["id"], "research")
        self.assertEqual(first["depends_on"], [])

    def test_code_review_appears_twice_with_distinct_targets(self):
        plan = Orchestrator.build_execution_plan("x")
        review_steps = [s for s in plan["steps"] if s["agent"] == "code_review"]
        self.assertEqual(len(review_steps), 2)
        targets = {s["kwargs"]["target_artifact"] for s in review_steps}
        self.assertEqual(targets, {"db_schema", "api_designer"})

    def test_bug_fixer_not_in_static_plan(self):
        plan = Orchestrator.build_execution_plan("x")
        agents_in_plan = {s["agent"] for s in plan["steps"]}
        self.assertNotIn("bug_fixer", agents_in_plan)

    def test_documentation_is_last_step(self):
        plan = Orchestrator.build_execution_plan("x")
        self.assertEqual(plan["steps"][-1]["id"], "documentation")


class InitializePipelineTests(TestCase):
    def test_creates_pipeline_linked_to_project(self):
        project = Project.objects.create(requirement="Build a chat app")
        pipeline = Orchestrator.initialize_pipeline(project)
        self.assertIsInstance(pipeline, Pipeline)
        self.assertEqual(pipeline.project_id, project.pk)

    def test_pipeline_execution_plan_matches_builder(self):
        project = Project.objects.create(requirement="r")
        pipeline = Orchestrator.initialize_pipeline(project)
        expected = Orchestrator.build_execution_plan("r")
        self.assertEqual(pipeline.execution_plan, expected)

    def test_initial_context_snapshot_has_requirement(self):
        project = Project.objects.create(requirement="My requirement")
        pipeline = Orchestrator.initialize_pipeline(project)
        self.assertEqual(pipeline.context_snapshot["requirement"], "My requirement")
        self.assertEqual(pipeline.context_snapshot["outputs"], {})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
