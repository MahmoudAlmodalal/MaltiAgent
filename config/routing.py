"""
WebSocket URL routing for Channels.
"""
from agents.consumers import websocket_urlpatterns as agent_ws_patterns

websocket_urlpatterns = list(agent_ws_patterns)
