"""
Channel-layer broadcast helper.

Wraps `channels.layers.get_channel_layer` + `async_to_sync` so callers can
push events to a group from sync code (e.g. Django signals, Celery tasks).

The helper is a no-op when:
- Channels is not installed (dev box without the package)
- settings.CHANNEL_LAYERS is not configured
- The channel layer is unreachable (e.g. Redis down)

This means you can call `broadcast_project_update()` freely from signals
during unit tests without any channels infrastructure.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# asgiref.sync is a Django dependency — always available.
from asgiref.sync import async_to_sync  # noqa: E402

try:
    from channels.layers import get_channel_layer

    _CHANNELS_AVAILABLE = True
except ImportError:
    _CHANNELS_AVAILABLE = False

    def get_channel_layer():  # type: ignore[misc]
        return None


EVENT_TYPE_AGENT_TASK = "agent_task_update"
EVENT_TYPE_PIPELINE = "pipeline_update"


def broadcast_project_update(project_id: int, event_type: str, payload: dict[str, Any]) -> None:
    """
    Send an event to the `project_<id>` channel group.

    Args:
        project_id:  The Project.pk this update relates to.
        event_type:  A logical type tag (e.g. "agent_task_update").
        payload:     JSON-serializable event body.

    The message dispatched to the channel layer has shape:
        {"type": "project.update", "event_type": event_type, "data": payload}

    Channel consumers receive it via their `project_update` handler.
    """
    if not _CHANNELS_AVAILABLE:
        return

    layer = get_channel_layer()
    if layer is None:
        return

    group_name = f"project_{project_id}"
    message = {
        "type": "project.update",
        "event_type": event_type,
        "data": payload,
    }

    try:
        async_to_sync(layer.group_send)(group_name, message)
    except Exception as exc:  # pragma: no cover - defensive; redis down etc.
        logger.warning(
            "broadcast_project_update failed (project=%d, type=%s): %s",
            project_id,
            event_type,
            exc,
        )
