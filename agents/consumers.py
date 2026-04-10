"""
WebSocket consumers for live agent pipeline updates.

Phase 8 fills in `ProjectStatusConsumer`. For Phase 1 we expose an empty
url pattern list so config.routing can import it without errors.
"""
from django.urls import re_path

websocket_urlpatterns: list = [
    # re_path(r"^ws/projects/(?P<project_id>\d+)/$", ProjectStatusConsumer.as_asgi()),
]
