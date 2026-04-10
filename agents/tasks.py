"""
Celery task wrappers around the synchronous pipeline_runner.

The tasks here are intentionally thin: every line of real logic lives in
`pipeline_runner.py` and `runner.py`, which are testable without Celery.

When Celery is not installed (dev box without the package), the `shared_task`
decorator becomes a no-op so the module still imports cleanly. In production,
the real Celery decorator routes each task to its own queue:
    orchestrator → high-priority entry point
    research, agents, review, testing, docs → per-stage queues
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Celery import shim
# ---------------------------------------------------------------------------
try:
    from celery import shared_task

    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False

    def shared_task(*args, **kwargs):  # type: ignore[no-redef]
        """
        No-op stand-in for celery.shared_task used when Celery isn't installed.
        Supports both `@shared_task` and `@shared_task(name=..., queue=...)` forms.
        Functions decorated with the stub gain a `.delay()` method that just calls
        the function synchronously, so calling code doesn't have to branch.
        """

        def _wrap(fn):
            def _delay(*a, **kw):
                return fn(*a, **kw)

            fn.delay = _delay  # type: ignore[attr-defined]
            return fn

        # Used as `@shared_task` without parentheses.
        if len(args) == 1 and callable(args[0]) and not kwargs:
            return _wrap(args[0])

        # Used as `@shared_task(name=..., queue=...)`.
        def _decorator(fn):
            return _wrap(fn)

        return _decorator


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------
@shared_task(name="agents.execute_pipeline", queue="orchestrator")
def execute_pipeline_task(pipeline_id: int) -> None:
    """
    Celery entry point: run the full pipeline for one Pipeline.
    Delegates to the synchronous runner.
    """
    from agents.pipeline_runner import execute_pipeline

    execute_pipeline(pipeline_id)


@shared_task(name="agents.run_single_agent", queue="agents")
def run_single_agent_task(
    pipeline_id: int, agent_type: str, **kwargs
) -> dict:
    """
    Celery entry point for re-running a single agent (used by retry endpoints).
    """
    from agents.implementations import AGENT_CLASSES
    from agents.runner import run_agent

    return run_agent(pipeline_id, AGENT_CLASSES[agent_type], **kwargs)
