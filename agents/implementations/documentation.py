import json

from agents.base_agent import BaseAgent


class DocumentationAgent(BaseAgent):
    """
    Technical Writer — synthesizes ALL upstream outputs into a single Markdown
    design document. The only agent that sees the entire context_snapshot.
    """

    agent_type = "documentation"
    # Largest output budget — produces a multi-section Markdown report.
    DEFAULT_MAX_TOKENS = 8000

    def _build_user_message(self, slice_data: dict) -> str:
        return json.dumps(slice_data, indent=2, ensure_ascii=False)
