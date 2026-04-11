"""
Integration tests for the Project API — Phase 9 + full end-to-end pipeline.

The heaviest test here exercises the FULL 9-agent pipeline through a single
`POST /api/projects/` call (sync fallback since Celery isn't installed) and
verifies that steps/, output/, and log/ endpoints all return sensible data.

Provider calls are stubbed via the same "smart chain" helper used in
test_pipeline_runner.py so no real HTTP traffic is made.
"""
import json
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
from rest_framework.test import APIClient  # noqa: E402

from agents.tests.test_pipeline_runner import make_smart_chain  # reuse  # noqa: E402
from projects.models import Project  # noqa: E402

User = get_user_model()


class ProjectAPIBasicTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user("alice_p", password="pw")
        self.client.force_authenticate(user=self.user)

    def test_list_empty_initially(self):
        resp = self.client.get("/api/projects/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        results = body["results"] if isinstance(body, dict) else body
        self.assertEqual(results, [])

    def test_unauthenticated_rejected(self):
        anon = APIClient()
        resp = anon.get("/api/projects/")
        self.assertEqual(resp.status_code, 403)

    def test_list_returns_only_current_users_projects(self):
        bob = User.objects.create_user("bob_p", password="pw")
        Project.objects.create(requirement="bob's project", created_by=bob)
        # Alice creates her own via API.
        with patch("agents.runner.build_chain_for_user", return_value=make_smart_chain()):
            resp = self.client.post(
                "/api/projects/", {"requirement": "alice's project"}, format="json"
            )
        self.assertEqual(resp.status_code, 201)

        resp = self.client.get("/api/projects/")
        body = resp.json()
        results = body["results"] if isinstance(body, dict) else body
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["requirement"], "alice's project")


class ProjectCreationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user("creator", password="pw")
        self.client.force_authenticate(user=self.user)

    def test_post_creates_project_and_pipeline(self):
        with patch("agents.runner.build_chain_for_user", return_value=make_smart_chain()):
            resp = self.client.post(
                "/api/projects/",
                {"requirement": "Build a note-taking app"},
                format="json",
            )

        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["requirement"], "Build a note-taking app")
        # Pipeline was attached.
        self.assertIn("pipeline", data)
        self.assertIsNotNone(data["pipeline"])
        self.assertIn("steps", data["pipeline"]["execution_plan"])

    def test_sync_fallback_runs_pipeline_end_to_end(self):
        """Without Celery, POST runs the full pipeline inline."""
        with patch("agents.runner.build_chain_for_user", return_value=make_smart_chain()):
            resp = self.client.post(
                "/api/projects/",
                {"requirement": "Build a todo app"},
                format="json",
            )

        project_id = resp.json()["id"]
        project = Project.objects.get(pk=project_id)
        self.assertEqual(project.status, Project.STATUS_COMPLETED)


class ProjectDetailActionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user("detail_user", password="pw")
        self.client.force_authenticate(user=self.user)

        with patch("agents.runner.build_chain_for_user", return_value=make_smart_chain()):
            resp = self.client.post(
                "/api/projects/",
                {"requirement": "Build an e2e test app"},
                format="json",
            )
        self.assertEqual(resp.status_code, 201)
        self.project_id = resp.json()["id"]

    def test_detail_includes_pipeline(self):
        resp = self.client.get(f"/api/projects/{self.project_id}/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["id"], self.project_id)
        self.assertIn("pipeline", data)

    def test_steps_returns_all_agent_tasks(self):
        resp = self.client.get(f"/api/projects/{self.project_id}/steps/")
        self.assertEqual(resp.status_code, 200)
        tasks = resp.json()
        # 9 steps for a happy-path run.
        self.assertEqual(len(tasks), 9)
        agent_types = {t["agent_type"] for t in tasks}
        self.assertIn("research", agent_types)
        self.assertIn("pm", agent_types)
        self.assertIn("documentation", agent_types)

    def test_steps_all_marked_done(self):
        resp = self.client.get(f"/api/projects/{self.project_id}/steps/")
        for t in resp.json():
            self.assertEqual(t["status"], "done")

    def test_output_returns_final_report(self):
        resp = self.client.get(f"/api/projects/{self.project_id}/output/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("# Overview", data["full_report"])
        self.assertIn("research", data["per_agent_outputs"])
        self.assertIn("documentation", data["per_agent_outputs"])

    def test_log_returns_compact_execution_log(self):
        resp = self.client.get(f"/api/projects/{self.project_id}/log/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["project_status"], "completed")
        self.assertEqual(len(data["steps"]), 9)
        for step in data["steps"]:
            self.assertIn("agent_type", step)
            self.assertIn("status", step)

    def test_detail_404_for_other_users_project(self):
        other = User.objects.create_user("outsider", password="pw")
        other_client = APIClient()
        other_client.force_authenticate(user=other)
        resp = other_client.get(f"/api/projects/{self.project_id}/")
        self.assertEqual(resp.status_code, 404)

    def test_output_404_before_pipeline_completes(self):
        """Create a project but simulate no final output."""
        from projects.models import Project as P

        project = P.objects.create(requirement="x", created_by=self.user)
        from agents.orchestrator import Orchestrator

        Orchestrator.initialize_pipeline(project)
        resp = self.client.get(f"/api/projects/{project.pk}/output/")
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
