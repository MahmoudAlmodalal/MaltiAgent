"""
Signal handlers — fan AgentTask / Pipeline updates out to WebSocket clients.

These handlers fire on every save of an AgentTask or Pipeline row and forward
a compact JSON payload to the channel group `project_<id>`. Consumers in
agents/consumers.py relay it to connected WebSocket clients.

Registered in agents/apps.py via `AgentsConfig.ready()`.
"""
from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from agents.broadcast import (
    EVENT_TYPE_AGENT_TASK,
    EVENT_TYPE_PIPELINE,
    broadcast_project_update,
)
from agents.models import AgentTask

logger = logging.getLogger(__name__)


@receiver(post_save, sender=AgentTask)
def on_agent_task_saved(sender, instance: AgentTask, created: bool, **kwargs) -> None:
    """
    Broadcast an AgentTask state change to its project's channel group.

    Fires on create AND update so the UI sees pending → running → done
    transitions without polling.
    """
    try:
        project_id = instance.pipeline.project_id
    except Exception:  # pragma: no cover - defensive: broken FK
        return

    payload = {
        "task_id": instance.pk,
        "agent_type": instance.agent_type,
        "target_artifact": instance.target_artifact,
        "status": instance.status,
        "duration_ms": instance.duration_ms,
        "retry_count": instance.retry_count,
        "provider_used": instance.provider_used,
        "error": instance.error if instance.status == AgentTask.STATUS_FAILED else "",
        "created": created,
    }
    broadcast_project_update(project_id, EVENT_TYPE_AGENT_TASK, payload)


# Pipeline signal is wired lazily to avoid a circular import at module load
# (projects.models imports from django.contrib.auth; agents app imports this
# module at ready() time, at which point projects.models is already loaded,
# so we can safely connect here).
def _connect_pipeline_signal() -> None:
    from projects.models import Pipeline

    @receiver(post_save, sender=Pipeline, weak=False, dispatch_uid="pipeline_broadcast")
    def on_pipeline_saved(sender, instance, created, **kwargs):
        payload = {
            "pipeline_id": instance.pk,
            "current_step": instance.current_step,
            "started_at": instance.started_at.isoformat() if instance.started_at else None,
            "finished_at": instance.finished_at.isoformat() if instance.finished_at else None,
        }
        broadcast_project_update(instance.project_id, EVENT_TYPE_PIPELINE, payload)


_connect_pipeline_signal()
