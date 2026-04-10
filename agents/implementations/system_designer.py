import json

from agents.base_agent import BaseAgent


class SystemDesignerAgent(BaseAgent):
    """
    Solution Architect — produces architecture style, tech stack, components.
    Sees user_stories + scope + risks (not the full research output).
    """

    agent_type = "system_designer"

    def _build_user_message(self, slice_data: dict) -> str:
        return json.dumps(slice_data, indent=2, ensure_ascii=False)
