"""
Signal handlers for the agents app.

Phase 8 will wire post_save on AgentTask to broadcast updates over the
Channels group `project_<id>`. For now this module exists so AgentsConfig.ready
has something to import without raising.
"""
