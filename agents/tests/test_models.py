"""
ORM-level tests for agents, projects, and provider_settings models.

Run with:
    DJANGO_SETTINGS_MODULE=config.settings_test python3 -m unittest agents.tests.test_models -v
"""
import os
import sys

# Bootstrap Django before any ORM imports.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_test")

import django  # noqa: E402

django.setup()

# Populate the :memory: SQLite database before any TestCase runs.
# This is required when using `python3 -m unittest discover` (which bypasses
# the Django test runner that would normally call create_test_db).
from django.core.management import call_command  # noqa: E402

call_command("migrate", "--run-syncdb", verbosity=0)

import unittest  # noqa: E402

from django.contrib.auth import get_user_model  # noqa: E402
from django.db import IntegrityError  # noqa: E402
from django.test import TestCase  # noqa: E402

User = get_user_model()


# ---------------------------------------------------------------------------
# Projects models
# ---------------------------------------------------------------------------
class ProjectModelTests(TestCase):
    def test_default_status_is_pending(self):
        from projects.models import Project

        p = Project.objects.create(requirement="Build a todo app")
        self.assertEqual(p.status, Project.STATUS_PENDING)

    def test_str_includes_status(self):
        from projects.models import Project

        p = Project.objects.create(requirement="Hello world", status="running")
        self.assertIn("running", str(p))

    def test_ordering_newest_first(self):
        from projects.models import Project

        p1 = Project.objects.create(requirement="First")
        p2 = Project.objects.create(requirement="Second")
        qs = list(Project.objects.all())
        self.assertEqual(qs[0].pk, p2.pk)
        self.assertEqual(qs[1].pk, p1.pk)


class PipelineModelTests(TestCase):
    def _make_project(self):
        from projects.models import Project

        return Project.objects.create(requirement="x")

    def test_pipeline_linked_to_project(self):
        from projects.models import Pipeline

        p = self._make_project()
        pipeline = Pipeline.objects.create(project=p)
        self.assertEqual(pipeline.project_id, p.pk)
        self.assertEqual(p.pipeline.pk, pipeline.pk)

    def test_context_snapshot_defaults_to_empty_dict(self):
        from projects.models import Pipeline

        p = self._make_project()
        pipeline = Pipeline.objects.create(project=p)
        self.assertEqual(pipeline.context_snapshot, {})

    def test_pipeline_stores_execution_plan(self):
        from projects.models import Pipeline

        p = self._make_project()
        plan = {"steps": ["research", "pm", "db_schema"]}
        pipeline = Pipeline.objects.create(project=p, execution_plan=plan)
        # Re-fetch from DB to confirm JSON round-trip.
        pipeline.refresh_from_db()
        self.assertEqual(pipeline.execution_plan, plan)


class FinalOutputModelTests(TestCase):
    def test_final_output_one_to_one_with_project(self):
        from projects.models import FinalOutput, Project

        p = Project.objects.create(requirement="x")
        fo = FinalOutput.objects.create(project=p, full_report="# Report")
        self.assertEqual(fo.project_id, p.pk)
        self.assertEqual(p.final_output.pk, fo.pk)

    def test_final_output_stores_per_agent_outputs(self):
        from projects.models import FinalOutput, Project

        p = Project.objects.create(requirement="x")
        data = {"research": {"summary": "foo"}}
        fo = FinalOutput.objects.create(project=p, per_agent_outputs=data)
        fo.refresh_from_db()
        self.assertEqual(fo.per_agent_outputs["research"]["summary"], "foo")


# ---------------------------------------------------------------------------
# AgentTask model
# ---------------------------------------------------------------------------
class AgentTaskModelTests(TestCase):
    def _make_pipeline(self):
        from projects.models import Pipeline, Project

        p = Project.objects.create(requirement="x")
        return Pipeline.objects.create(project=p)

    def test_agent_task_creation(self):
        from agents.models import AgentTask

        pipeline = self._make_pipeline()
        task = AgentTask.objects.create(pipeline=pipeline, agent_type="research")
        self.assertEqual(task.status, AgentTask.STATUS_PENDING)
        self.assertEqual(task.retry_count, 0)
        self.assertEqual(task.duration_ms, 0)

    def test_all_agent_types_are_valid_choices(self):
        from agents.context_manager import ALL_AGENTS
        from agents.models import AgentTask

        pipeline = self._make_pipeline()
        valid = {choice[0] for choice in AgentTask.AGENT_CHOICES}
        for agent in ALL_AGENTS:
            self.assertIn(agent, valid, f"{agent!r} not in AGENT_CHOICES")

    def test_input_slice_stored_as_json(self):
        from agents.models import AgentTask

        pipeline = self._make_pipeline()
        sl = {"requirement": "build x", "research": {"summary": "short"}}
        task = AgentTask.objects.create(
            pipeline=pipeline, agent_type="pm", input_slice=sl
        )
        task.refresh_from_db()
        self.assertEqual(task.input_slice["research"]["summary"], "short")

    def test_target_artifact_for_code_review(self):
        from agents.models import AgentTask

        pipeline = self._make_pipeline()
        task = AgentTask.objects.create(
            pipeline=pipeline,
            agent_type="code_review",
            target_artifact="db_schema",
        )
        task.refresh_from_db()
        self.assertEqual(task.target_artifact, "db_schema")

    def test_ordering_by_created_at(self):
        from agents.models import AgentTask

        pipeline = self._make_pipeline()
        t1 = AgentTask.objects.create(pipeline=pipeline, agent_type="research")
        t2 = AgentTask.objects.create(pipeline=pipeline, agent_type="pm")
        tasks = list(AgentTask.objects.filter(pipeline=pipeline))
        self.assertEqual(tasks[0].pk, t1.pk)
        self.assertEqual(tasks[1].pk, t2.pk)


# ---------------------------------------------------------------------------
# ProviderConfig + EncryptedTextField
# ---------------------------------------------------------------------------
class ProviderConfigModelTests(TestCase):
    def _make_user(self, username="alice"):
        return User.objects.create_user(username=username, password="pw")

    def test_create_provider_config(self):
        from provider_settings.models import ProviderConfig

        user = self._make_user()
        pc = ProviderConfig.objects.create(
            user=user,
            provider="groq",
            api_key="gsk_test_key_123",
            model_name="llama-3.3-70b-versatile",
        )
        self.assertEqual(pc.provider, "groq")
        self.assertEqual(pc.fallback_order, 100)

    def test_encrypted_field_round_trip(self):
        """api_key saved as ciphertext, read back as plaintext."""
        from provider_settings.models import ProviderConfig

        user = self._make_user()
        plaintext = "super-secret-api-key"
        pc = ProviderConfig.objects.create(
            user=user,
            provider="groq",
            api_key=plaintext,
            model_name="llama-3.3-70b-versatile",
        )
        # Re-fetch to ensure we're reading from DB, not from instance cache.
        pc_fresh = ProviderConfig.objects.get(pk=pc.pk)
        self.assertEqual(pc_fresh.api_key, plaintext)

    def test_encrypted_field_ciphertext_differs_from_plaintext(self):
        """Raw DB value must NOT equal the plaintext."""
        from django.db import connection

        from provider_settings.models import ProviderConfig

        user = self._make_user()
        plaintext = "my-plaintext-key"
        pc = ProviderConfig.objects.create(
            user=user,
            provider="groq",
            api_key=plaintext,
            model_name="llama-3.3-70b-versatile",
        )
        # Read the raw column value bypassing field descriptors.
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT api_key FROM provider_settings_providerconfig WHERE id = %s",
                [pc.pk],
            )
            raw = cursor.fetchone()[0]
        self.assertNotEqual(raw, plaintext, "api_key stored as plaintext — encryption broken")
        # Fernet tokens are base64 strings starting with gAAA...
        self.assertTrue(raw.startswith("gAA"), f"Expected Fernet token, got: {raw[:20]!r}")

    def test_encrypted_field_empty_string_stored_as_empty(self):
        """Empty api_key should remain empty (not be encrypted to garbage)."""
        from provider_settings.models import ProviderConfig

        user = self._make_user()
        pc = ProviderConfig.objects.create(
            user=user,
            provider="ollama",
            api_key="",
            model_name="llama3.1",
        )
        pc_fresh = ProviderConfig.objects.get(pk=pc.pk)
        self.assertEqual(pc_fresh.api_key, "")

    def test_unique_constraint_user_provider(self):
        """Two ProviderConfigs for the same user+provider must raise IntegrityError."""
        from provider_settings.models import ProviderConfig

        user = self._make_user()
        ProviderConfig.objects.create(
            user=user, provider="groq", api_key="k1", model_name="m1"
        )
        with self.assertRaises(IntegrityError):
            ProviderConfig.objects.create(
                user=user, provider="groq", api_key="k2", model_name="m2"
            )

    def test_ordering_by_fallback_order(self):
        from provider_settings.models import ProviderConfig

        user = self._make_user()
        ProviderConfig.objects.create(
            user=user, provider="anthropic", api_key="", model_name="m", fallback_order=3
        )
        ProviderConfig.objects.create(
            user=user, provider="groq", api_key="", model_name="m", fallback_order=1
        )
        ProviderConfig.objects.create(
            user=user, provider="openrouter", api_key="", model_name="m", fallback_order=2
        )
        ordered = list(
            ProviderConfig.objects.filter(user=user).values_list("provider", flat=True)
        )
        self.assertEqual(ordered, ["groq", "openrouter", "anthropic"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
