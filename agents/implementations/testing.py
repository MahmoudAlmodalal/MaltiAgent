import json

from agents.base_agent import BaseAgent


class TestingAgent(BaseAgent):
    """
    QA Engineer — produces unit_tests + integration_tests covering the DB schema
    and API design. Sees both schema and API together (not the user stories).
    """

    agent_type = "testing"
    DEFAULT_MAX_TOKENS = 6000

    def _build_user_message(self, slice_data: dict) -> str:
        return json.dumps(slice_data, indent=2, ensure_ascii=False)
