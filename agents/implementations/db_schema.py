import json

from agents.base_agent import BaseAgent


class DBSchemaAgent(BaseAgent):
    """
    Database Engineer — produces models, relationships, indexes.
    Sees only the architecture (not the user stories or research).
    """

    agent_type = "db_schema"
    # Schema generation benefits from more output budget than the default.
    DEFAULT_MAX_TOKENS = 6000

    def _build_user_message(self, slice_data: dict) -> str:
        return json.dumps(slice_data, indent=2, ensure_ascii=False)
