import json

from agents.base_agent import BaseAgent


class ResearchAgent(BaseAgent):
    """
    Senior Research Analyst — produces summary, risks, ambiguities, best_practices
    from a raw requirement. Always the first agent in the pipeline.
    """

    agent_type = "research"
    DEFAULT_TEMPERATURE = 0.3  # slightly more creative for risk discovery

    def _build_user_message(self, slice_data: dict) -> str:
        return json.dumps(slice_data, indent=2, ensure_ascii=False)
