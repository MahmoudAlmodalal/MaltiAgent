import json

from agents.base_agent import BaseAgent


class BugFixerAgent(BaseAgent):
    """
    Bug Fixer — applies the latest code review's suggestions to an artifact and
    produces a revised version of the same shape.

    Invoked dynamically by Phase 7's task layer when code_review or testing fails.
    Not in the static execution plan.
    """

    agent_type = "bug_fixer"
    DEFAULT_TEMPERATURE = 0.1
    DEFAULT_MAX_TOKENS = 6000

    def _build_user_message(self, slice_data: dict) -> str:
        return json.dumps(slice_data, indent=2, ensure_ascii=False)
