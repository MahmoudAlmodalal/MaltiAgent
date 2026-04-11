"""
Project API viewsets.

Endpoints:
  GET  /api/projects/                → list current user's projects
  POST /api/projects/                → create a Project + Pipeline, launch execution
  GET  /api/projects/{id}/           → project detail (with pipeline)
  GET  /api/projects/{id}/steps/     → all AgentTask rows for the project
  GET  /api/projects/{id}/output/    → the FinalOutput (404 until ready)
  GET  /api/projects/{id}/log/       → chronological execution log (steps + current)
"""
from __future__ import annotations

import logging

from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from agents.models import AgentTask
from agents.orchestrator import Orchestrator

from .models import FinalOutput, Project
from .serializers import (
    AgentTaskSerializer,
    FinalOutputSerializer,
    ProjectSerializer,
)

logger = logging.getLogger(__name__)


class ProjectViewSet(viewsets.ModelViewSet):
    """
    CRUD + custom actions for Projects.

    POST to the list endpoint creates a Project, initializes its Pipeline via
    the Orchestrator, and kicks off execution. When Celery is installed the
    task is dispatched via `.delay()`; otherwise it runs synchronously (useful
    for development and tests).
    """

    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Project.objects.filter(created_by=self.request.user).select_related(
            "pipeline"
        )

    def perform_create(self, serializer):
        """Create Project → initialize Pipeline → launch execution."""
        project = serializer.save(created_by=self.request.user)
        Orchestrator.initialize_pipeline(project)
        self._launch_pipeline(project.pk)

    @staticmethod
    def _launch_pipeline(project_id: int) -> None:
        """
        Kick off pipeline execution. Uses Celery's .delay() when available;
        falls back to in-process execution otherwise.
        """
        from agents.tasks import CELERY_AVAILABLE, execute_pipeline_task

        project = Project.objects.select_related("pipeline").get(pk=project_id)
        pipeline_id = project.pipeline.pk

        if CELERY_AVAILABLE:
            execute_pipeline_task.delay(pipeline_id)
        else:
            # Synchronous fallback — try it but swallow exceptions so the POST
            # still returns 201. Status updates are visible via /steps/ and /log/.
            try:
                execute_pipeline_task(pipeline_id)
            except Exception:
                logger.exception(
                    "Synchronous pipeline execution failed for project %d", project_id
                )

    @action(detail=True, methods=["get"])
    def steps(self, request, pk=None):
        """Return every AgentTask row for this project, in order."""
        project = get_object_or_404(self.get_queryset(), pk=pk)
        tasks = AgentTask.objects.filter(pipeline__project=project).order_by(
            "created_at"
        )
        serializer = AgentTaskSerializer(tasks, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def output(self, request, pk=None):
        """Return the final Markdown report. 404 until the pipeline finishes."""
        project = get_object_or_404(self.get_queryset(), pk=pk)
        try:
            final = project.final_output
        except FinalOutput.DoesNotExist:
            return Response(
                {"detail": "Final output not yet available."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = FinalOutputSerializer(final)
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def log(self, request, pk=None):
        """Return a compact execution log: current_step + per-task status."""
        project = get_object_or_404(self.get_queryset(), pk=pk)
        pipeline = project.pipeline
        tasks = AgentTask.objects.filter(pipeline=pipeline).order_by("created_at")
        return Response(
            {
                "project_status": project.status,
                "current_step": pipeline.current_step,
                "started_at": pipeline.started_at,
                "finished_at": pipeline.finished_at,
                "steps": [
                    {
                        "agent_type": t.agent_type,
                        "target_artifact": t.target_artifact,
                        "status": t.status,
                        "duration_ms": t.duration_ms,
                        "error": t.error,
                    }
                    for t in tasks
                ],
            }
        )
