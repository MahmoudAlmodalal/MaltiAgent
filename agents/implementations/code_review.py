import json

from agents.base_agent import BaseAgent


class CodeReviewAgent(BaseAgent):
    """
    Senior Code Reviewer — produces issues + severity + suggested fixes for one
    specific artifact (db_schema or api_designer).

    Always invoked with `target_artifact` kwarg pointing at the artifact under review.
    """

    agent_type = "code_review"
    # Reviewers should be deterministic — minimal temperature.
    DEFAULT_TEMPERATURE = 0.0

    def _build_user_message(self, slice_data: dict) -> str:
        return json.dumps(slice_data, indent=2, ensure_ascii=False)
