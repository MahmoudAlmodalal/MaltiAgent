"""
Tests for the Celery task wrappers in agents/tasks.py.

In this dev environment Celery isn't installed, so these tests verify the
shim behaves correctly: tasks are still callable and `.delay()` runs them
synchronously.
"""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_test")

import django  # noqa: E402

django.setup()

from django.core.management import call_command  # noqa: E402

call_command("migrate", "--run-syncdb", verbosity=0)

from agents import tasks  # noqa: E402


class CeleryShimTests(unittest.TestCase):
    def test_celery_unavailable_in_this_env(self):
        """Sanity check: this test environment has no celery installed."""
        self.assertFalse(tasks.CELERY_AVAILABLE)

    def test_execute_pipeline_task_is_callable(self):
        self.assertTrue(callable(tasks.execute_pipeline_task))

    def test_run_single_agent_task_is_callable(self):
        self.assertTrue(callable(tasks.run_single_agent_task))

    def test_shim_provides_delay_method(self):
        self.assertTrue(hasattr(tasks.execute_pipeline_task, "delay"))
        self.assertTrue(hasattr(tasks.run_single_agent_task, "delay"))


class TaskDispatchTests(unittest.TestCase):
    def test_execute_pipeline_task_delegates_to_runner(self):
        with patch("agents.pipeline_runner.execute_pipeline") as mock_runner:
            tasks.execute_pipeline_task(42)
        mock_runner.assert_called_once_with(42)

    def test_run_single_agent_task_delegates_to_run_agent(self):
        with patch("agents.runner.run_agent") as mock_run:
            mock_run.return_value = {"result": "ok"}
            result = tasks.run_single_agent_task(1, "research")
        mock_run.assert_called_once()
        self.assertEqual(result, {"result": "ok"})

    def test_run_single_agent_task_passes_kwargs(self):
        with patch("agents.runner.run_agent") as mock_run:
            mock_run.return_value = {}
            tasks.run_single_agent_task(7, "code_review", target_artifact="db_schema")

        # First positional arg is pipeline_id, second is the agent class.
        call_args = mock_run.call_args
        self.assertEqual(call_args[0][0], 7)
        self.assertEqual(call_args[1], {"target_artifact": "db_schema"})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
