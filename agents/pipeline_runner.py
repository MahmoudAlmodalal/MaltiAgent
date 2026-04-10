"""
Pipeline runner — synchronous orchestration of an entire pipeline.

This module contains the actual execution logic. Celery tasks in `tasks.py`
are thin wrappers around `execute_pipeline()`. Keeping the logic here means:
1. The pipeline is fully testable without Celery installed.
2. We can run the pipeline synchronously in tests, management commands, or
   debugging sessions.
3. The Celery layer is just transport — it can be swapped for any task queue.

Review / bug-fix loop:
    For each `code_review` step in the plan:
      run code_review
      if approved → continue
      else:
        for attempt in range(MAX_BUGFIX_RETRIES):
          run bug_fixer
          replace artifact in context with bug_fixer's revised_artifact
          re-run code_review
          if approved → break
        else: log warning and continue (don't block the pipeline)
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.utils import timezone

logger = logging.getLogger(__name__)

MAX_BUGFIX_RETRIES = 2

if TYPE_CHECKING:
    from projects.models import Pipeline


def execute_pipeline(pipeline_id: int) -> None:
    """
    Run the entire pipeline for one Pipeline, end to end.

    Updates Project.status as it progresses (running → completed/failed).
    On success, persists a FinalOutput record.
    On failure, marks Project.status=failed and re-raises so callers
    (e.g. Celery) can record the error.
    """
    from projects.models import Pipeline, Project

    pipeline = Pipeline.objects.select_related("project").get(pk=pipeline_id)
    project = pipeline.project

    project.status = Project.STATUS_RUNNING
    project.save(update_fields=["status"])
    pipeline.started_at = timezone.now()
    pipeline.save(update_fields=["started_at"])

    try:
        plan = pipeline.execution_plan
        for step in plan["steps"]:
            _run_step(pipeline, step)

        _finalize(pipeline)

        project.status = Project.STATUS_COMPLETED
        project.save(update_fields=["status"])
    except Exception:
        logger.exception("Pipeline %d failed", pipeline_id)
        project.status = Project.STATUS_FAILED
        project.save(update_fields=["status"])
        raise
    finally:
        pipeline.finished_at = timezone.now()
        pipeline.save(update_fields=["finished_at"])


# ---------------------------------------------------------------------------
# Step execution
# ---------------------------------------------------------------------------
def _run_step(pipeline: "Pipeline", step: dict) -> None:
    """
    Run one step from the execution plan. If the step is a code_review and
    the review is not approved, kick off the bug-fix loop for the same target.
    """
    from agents.implementations import AGENT_CLASSES
    from agents.runner import run_agent

    agent_class = AGENT_CLASSES[step["agent"]]
    kwargs = step.get("kwargs", {})

    output = run_agent(pipeline.pk, agent_class, **kwargs)

    # Trigger bug-fix loop on a non-approving review.
    if step["agent"] == "code_review" and not output.get("approved", True):
        target_artifact = kwargs.get("target_artifact")
        if target_artifact:
            _run_bugfix_loop(pipeline, target_artifact)


def _run_bugfix_loop(pipeline: "Pipeline", target_artifact: str) -> None:
    """
    Try up to MAX_BUGFIX_RETRIES rounds of bug_fixer + code_review.

    On any underlying failure, log a warning and return — never block the
    pipeline. The artifact under review may end up in an unfixed state, which
    is fine: downstream agents see whatever the last successful agent produced.
    """
    from agents.implementations import AGENT_CLASSES
    from agents.runner import run_agent

    for attempt in range(1, MAX_BUGFIX_RETRIES + 1):
        try:
            fix_output = run_agent(
                pipeline.pk,
                AGENT_CLASSES["bug_fixer"],
                target_artifact=target_artifact,
            )
        except Exception as exc:
            logger.warning(
                "Bug fixer failed on attempt %d for %s: %s",
                attempt,
                target_artifact,
                exc,
            )
            return

        # Replace the artifact in the snapshot with the revised version.
        revised = fix_output.get("revised_artifact")
        if revised is not None:
            _replace_artifact_in_snapshot(pipeline, target_artifact, revised)

        # Re-run code_review against the revised artifact.
        try:
            review_output = run_agent(
                pipeline.pk,
                AGENT_CLASSES["code_review"],
                target_artifact=target_artifact,
            )
        except Exception as exc:
            logger.warning(
                "Re-review failed on attempt %d for %s: %s",
                attempt,
                target_artifact,
                exc,
            )
            return

        if review_output.get("approved", False):
            logger.info(
                "Bug fix loop succeeded for %s after %d attempt(s)",
                target_artifact,
                attempt,
            )
            return

    logger.warning(
        "Bug fix loop exhausted (%d attempts) for %s — proceeding with last revision",
        MAX_BUGFIX_RETRIES,
        target_artifact,
    )


def _replace_artifact_in_snapshot(
    pipeline: "Pipeline", target_artifact: str, revised: dict
) -> None:
    """
    Overwrite the named artifact in the pipeline's context_snapshot with the
    bug-fixer's revised version, then persist.
    """
    pipeline.refresh_from_db(fields=["context_snapshot"])
    snapshot = pipeline.context_snapshot
    outputs = snapshot.setdefault("outputs", {})
    outputs[target_artifact] = revised
    pipeline.context_snapshot = snapshot
    pipeline.save(update_fields=["context_snapshot"])


# ---------------------------------------------------------------------------
# Finalization
# ---------------------------------------------------------------------------
def _finalize(pipeline: "Pipeline") -> None:
    """
    Build a FinalOutput from the documentation agent's output. The Markdown
    report is taken from `report_markdown`; raw per-agent outputs are stored
    alongside for programmatic access.
    """
    from projects.models import FinalOutput

    pipeline.refresh_from_db(fields=["context_snapshot"])
    outputs = pipeline.context_snapshot.get("outputs", {})
    docs = outputs.get("documentation", {}) or {}

    FinalOutput.objects.update_or_create(
        project=pipeline.project,
        defaults={
            "full_report": docs.get("report_markdown", ""),
            "per_agent_outputs": outputs,
        },
    )
