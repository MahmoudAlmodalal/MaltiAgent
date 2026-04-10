"""
Orchestrator — builds the static execution plan for a Pipeline.

The plan is a JSON-serializable DAG that Phase 7 (Celery) will use to wire
chain/chord composition. The plan is intentionally fixed for now: every project
runs the same 9-agent flow. A future Orchestrator could plug in an LLM step
to customize the DAG per requirement.

Note: bug_fixer is NOT in the static plan — it's invoked dynamically by the
Celery task layer when code_review or testing reports failure.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from projects.models import Pipeline, Project


class Orchestrator:
    PLAN_VERSION = 1

    @staticmethod
    def build_execution_plan(requirement: str) -> dict:
        """
        Returns a JSON-serializable execution plan describing the ordered DAG.
        Each step has:
            id          — unique identifier within the plan
            agent       — which agent_type to instantiate
            depends_on  — list of step ids that must complete first
            kwargs      — optional kwargs for ContextManager.get_slice
                          (used by code_review to pass target_artifact)
        """
        return {
            "version": Orchestrator.PLAN_VERSION,
            "requirement_preview": requirement[:120],
            "steps": [
                {"id": "research", "agent": "research", "depends_on": []},
                {"id": "pm", "agent": "pm", "depends_on": ["research"]},
                {
                    "id": "system_designer",
                    "agent": "system_designer",
                    "depends_on": ["pm"],
                },
                {
                    "id": "db_schema",
                    "agent": "db_schema",
                    "depends_on": ["system_designer"],
                },
                {
                    "id": "review_db",
                    "agent": "code_review",
                    "depends_on": ["db_schema"],
                    "kwargs": {"target_artifact": "db_schema"},
                },
                {
                    "id": "api_designer",
                    "agent": "api_designer",
                    "depends_on": ["review_db"],
                },
                {
                    "id": "review_api",
                    "agent": "code_review",
                    "depends_on": ["api_designer"],
                    "kwargs": {"target_artifact": "api_designer"},
                },
                {
                    "id": "testing",
                    "agent": "testing",
                    "depends_on": ["review_api"],
                },
                {
                    "id": "documentation",
                    "agent": "documentation",
                    "depends_on": ["testing"],
                },
            ],
        }

    @classmethod
    def initialize_pipeline(cls, project: "Project") -> "Pipeline":
        """
        Create a Pipeline for a Project, populating execution_plan and the
        initial context_snapshot. The Pipeline is saved before returning.
        """
        from projects.models import Pipeline

        plan = cls.build_execution_plan(project.requirement)
        pipeline = Pipeline.objects.create(
            project=project,
            execution_plan=plan,
            current_step="",
            context_snapshot={
                "requirement": project.requirement,
                "outputs": {},
            },
        )
        return pipeline
