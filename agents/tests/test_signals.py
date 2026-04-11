"""
Tests for Django signal handlers that fan pipeline updates out to WebSocket
clients via the broadcast shim.

Strategy: patch `agents.signals.broadcast_project_update` and verify it's
invoked with the right arguments when AgentTask / Pipeline rows are saved.
"""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_test")

import django  # noqa: E402

django.setup()

from django.core.management import call_command  # noqa: E402

call_command("migrate", "--run-syncdb", verbosity=0)

from django.contrib.auth import get_user_model  # noqa: E402
from django.test import TestCase  # noqa: E402

from agents.models import AgentTask  # noqa: E402
from projects.models import Pipeline, Project  # noqa: E402

User = get_user_model()


class AgentTaskSignalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("signals_user", password="pw")
        self.project = Project.objects.create(
            requirement="Build a todo app", created_by=self.user
        )
        self.pipeline = Pipeline.objects.create(project=self.project)

    def test_agent_task_save_triggers_broadcast(self):
        with patch("agents.signals.broadcast_project_update") as mock_bcast:
            AgentTask.objects.create(
                pipeline=self.pipeline, agent_type="research"
            )

        self.assertTrue(mock_bcast.called)
        args, _ = mock_bcast.call_args
        self.assertEqual(args[0], self.project.pk)
        self.assertEqual(args[1], "agent_task_update")

    def test_agent_task_broadcast_payload_has_expected_fields(self):
        with patch("agents.signals.broadcast_project_update") as mock_bcast:
            task = AgentTask.objects.create(
                pipeline=self.pipeline,
                agent_type="db_schema",
                status=AgentTask.STATUS_RUNNING,
                target_artifact="",
            )

        payload = mock_bcast.call_args[0][2]
        self.assertEqual(payload["task_id"], task.pk)
        self.assertEqual(payload["agent_type"], "db_schema")
        self.assertEqual(payload["status"], AgentTask.STATUS_RUNNING)
        self.assertTrue(payload["created"])

    def test_agent_task_update_broadcasts_with_created_false(self):
        task = AgentTask.objects.create(pipeline=self.pipeline, agent_type="pm")
        with patch("agents.signals.broadcast_project_update") as mock_bcast:
            task.status = AgentTask.STATUS_DONE
            task.save()

        # The most recent call should have created=False.
        payload = mock_bcast.call_args[0][2]
        self.assertFalse(payload["created"])
        self.assertEqual(payload["status"], AgentTask.STATUS_DONE)

    def test_failed_task_broadcast_includes_error(self):
        with patch("agents.signals.broadcast_project_update") as mock_bcast:
            AgentTask.objects.create(
                pipeline=self.pipeline,
                agent_type="research",
                status=AgentTask.STATUS_FAILED,
                error="network timeout",
            )

        payload = mock_bcast.call_args[0][2]
        self.assertEqual(payload["error"], "network timeout")

    def test_done_task_broadcast_omits_error(self):
        with patch("agents.signals.broadcast_project_update") as mock_bcast:
            AgentTask.objects.create(
                pipeline=self.pipeline,
                agent_type="research",
                status=AgentTask.STATUS_DONE,
                error="",
            )

        payload = mock_bcast.call_args[0][2]
        self.assertEqual(payload["error"], "")


class PipelineSignalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("pipeline_sig", password="pw")
        self.project = Project.objects.create(
            requirement="x", created_by=self.user
        )

    def test_pipeline_save_triggers_broadcast(self):
        with patch("agents.signals.broadcast_project_update") as mock_bcast:
            Pipeline.objects.create(project=self.project)

        # Find the pipeline_update call.
        pipeline_calls = [
            c for c in mock_bcast.call_args_list if c.args[1] == "pipeline_update"
        ]
        self.assertTrue(pipeline_calls)
        args = pipeline_calls[-1].args
        self.assertEqual(args[0], self.project.pk)

    def test_pipeline_broadcast_payload_has_current_step(self):
        pipeline = Pipeline.objects.create(project=self.project)
        with patch("agents.signals.broadcast_project_update") as mock_bcast:
            pipeline.current_step = "research"
            pipeline.save()

        pipeline_calls = [
            c for c in mock_bcast.call_args_list if c.args[1] == "pipeline_update"
        ]
        payload = pipeline_calls[-1].args[2]
        self.assertEqual(payload["current_step"], "research")
        self.assertEqual(payload["pipeline_id"], pipeline.pk)


class ConsumerImportTests(unittest.TestCase):
    """The consumers module must import cleanly even without channels."""

    def test_consumers_module_imports(self):
        from agents import consumers
        self.assertEqual(consumers.websocket_urlpatterns, [])

    def test_project_status_consumer_class_defined(self):
        from agents.consumers import ProjectStatusConsumer
        self.assertTrue(hasattr(ProjectStatusConsumer, "connect"))
        self.assertTrue(hasattr(ProjectStatusConsumer, "disconnect"))
        self.assertTrue(hasattr(ProjectStatusConsumer, "project_update"))

    def test_as_asgi_raises_without_channels(self):
        from agents.consumers import ProjectStatusConsumer
        with self.assertRaises(RuntimeError):
            ProjectStatusConsumer.as_asgi()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
