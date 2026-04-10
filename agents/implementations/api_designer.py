import json

from agents.base_agent import BaseAgent


class APIDesignerAgent(BaseAgent):
    """
    API Architect — produces endpoints, serializers, urls.
    Sees only the approved DB schema (not earlier stages).
    """

    agent_type = "api_designer"
    DEFAULT_MAX_TOKENS = 6000

    def _build_user_message(self, slice_data: dict) -> str:
        return json.dumps(slice_data, indent=2, ensure_ascii=False)
