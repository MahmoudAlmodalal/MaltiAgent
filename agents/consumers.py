"""
WebSocket consumers for live agent pipeline updates.

One consumer per project: `ws://.../ws/projects/<id>/` joins the channel group
`project_<id>` and forwards any broadcast from signals to the connected client.

Channels is an optional dependency in the dev environment — when it's not
installed, the module degrades gracefully:
- `ProjectStatusConsumer` becomes a stub that raises if anyone tries to wire it
- `websocket_urlpatterns` is an empty list

This keeps `config.routing` importable in tests that don't need channels.
"""
from __future__ import annotations

try:
    from channels.generic.websocket import AsyncJsonWebsocketConsumer

    _CHANNELS_AVAILABLE = True
except ImportError:
    _CHANNELS_AVAILABLE = False

    class AsyncJsonWebsocketConsumer:  # type: ignore[no-redef]
        """Stub base class when channels isn't installed."""

        scope: dict

        @classmethod
        def as_asgi(cls, **kwargs):
            raise RuntimeError(
                "channels is not installed — ProjectStatusConsumer cannot be used"
            )


class ProjectStatusConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket consumer for live project pipeline updates.

    URL:  ws://.../ws/projects/<project_id>/

    On connect:
        - Parses `project_id` from the URL
        - Joins the channel group `project_<project_id>`
        - Accepts the connection

    Group messages dispatched with `{"type": "project.update", ...}`
    are delivered to the client as JSON via the `project_update` handler.
    """

    async def connect(self) -> None:
        self.project_id = int(self.scope["url_route"]["kwargs"]["project_id"])
        self.group_name = f"project_{self.project_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code) -> None:
        if getattr(self, "group_name", None):
            await self.channel_layer.group_discard(
                self.group_name, self.channel_name
            )

    async def project_update(self, event: dict) -> None:
        """
        Handler for messages sent with {"type": "project.update", ...}.
        Forwards the payload to the client.
        """
        await self.send_json(
            {
                "event_type": event.get("event_type", "unknown"),
                "data": event.get("data", {}),
            }
        )


# WebSocket URL patterns — only populated when channels is available.
websocket_urlpatterns: list = []

if _CHANNELS_AVAILABLE:
    from django.urls import re_path

    websocket_urlpatterns = [
        re_path(
            r"^ws/projects/(?P<project_id>\d+)/$",
            ProjectStatusConsumer.as_asgi(),
        ),
    ]
