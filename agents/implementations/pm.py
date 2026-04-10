import json

from agents.base_agent import BaseAgent


class PMAgent(BaseAgent):
    """
    Product Manager — converts research findings into user_stories + scope.
    Sees only the requirement + research summary/risks/ambiguities (not best_practices).
    """

    agent_type = "pm"

    def _build_user_message(self, slice_data: dict) -> str:
        return json.dumps(slice_data, indent=2, ensure_ascii=False)
