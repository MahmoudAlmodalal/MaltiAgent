"""
Context Manager — central state slicer for the agent pipeline.

Each agent only sees the slice of accumulated context that it actually needs.
This keeps prompts small (cheap and within token limits) and prevents irrelevant
context from polluting downstream agents.

Design notes
------------
- Pure Python: zero Django/ORM dependency. Pipeline.context_snapshot stores the
  dict returned by `snapshot()` and the manager rehydrates from it.
- The slice rules are the source of truth — see SLICE_KEYS below and the
  `get_slice` method. Tests in agents/tests/test_context_manager.py exercise
  every rule.
- The token guard accepts an optional `summarizer` callable so that Phase 4's
  provider layer can plug in real LLM summarization without this module having
  to import provider code.
"""
from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Callable, Optional

# Optional tiktoken for accurate counts; fall back to a heuristic.
try:  # pragma: no cover - import-time branch
    import tiktoken

    _ENCODING = tiktoken.get_encoding("cl100k_base")

    def _count_tokens(text: str) -> int:
        return len(_ENCODING.encode(text))

except Exception:  # pragma: no cover - exercised when tiktoken absent

    def _count_tokens(text: str) -> int:
        # ~4 chars per token is the standard rough estimate for English / code.
        return max(1, len(text) // 4)


# ---------------------------------------------------------------------------
# Agent type constants — keep in sync with AgentTask.AGENT_TYPES (Phase 3)
# ---------------------------------------------------------------------------
AGENT_RESEARCH = "research"
AGENT_PM = "pm"
AGENT_SYSTEM_DESIGNER = "system_designer"
AGENT_DB_SCHEMA = "db_schema"
AGENT_API_DESIGNER = "api_designer"
AGENT_CODE_REVIEW = "code_review"
AGENT_BUG_FIXER = "bug_fixer"
AGENT_TESTING = "testing"
AGENT_DOCUMENTATION = "documentation"

ALL_AGENTS = (
    AGENT_RESEARCH,
    AGENT_PM,
    AGENT_SYSTEM_DESIGNER,
    AGENT_DB_SCHEMA,
    AGENT_API_DESIGNER,
    AGENT_CODE_REVIEW,
    AGENT_BUG_FIXER,
    AGENT_TESTING,
    AGENT_DOCUMENTATION,
)

# Agents whose outputs accumulate as a list rather than overwriting.
LIST_AGENTS = frozenset({AGENT_CODE_REVIEW, AGENT_BUG_FIXER})


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
class UnknownAgentError(ValueError):
    """Raised when an unknown agent_type is requested."""


class MissingContextError(KeyError):
    """Raised when a required predecessor's output is missing from the snapshot."""


Summarizer = Callable[[str, int], str]


# ---------------------------------------------------------------------------
# ContextManager
# ---------------------------------------------------------------------------
class ContextManager:
    """
    Slice-aware accumulator for the agent pipeline.

    Usage:
        cm = ContextManager(requirement="Build a todo app")
        cm.save_output("research", {"summary": ..., "risks": [...]})
        slice_for_pm = cm.get_slice("pm")
        cm.save_output("pm", {"user_stories": [...]})
        ...
        snapshot = cm.snapshot()   # JSON-serializable, persist to Pipeline
    """

    DEFAULT_MAX_SLICE_TOKENS = 8000

    def __init__(
        self,
        requirement: str = "",
        snapshot: Optional[dict] = None,
        *,
        max_slice_tokens: int = DEFAULT_MAX_SLICE_TOKENS,
        summarizer: Optional[Summarizer] = None,
    ):
        if snapshot is not None:
            self._state: dict[str, Any] = deepcopy(snapshot)
            if requirement and not self._state.get("requirement"):
                self._state["requirement"] = requirement
        else:
            self._state = {"requirement": requirement, "outputs": {}}

        # Defensive: ensure invariants whether we hydrated or initialized fresh.
        self._state.setdefault("requirement", "")
        self._state.setdefault("outputs", {})

        self._max_slice_tokens = max_slice_tokens
        self._summarizer = summarizer

    # ------------------------------------------------------------------
    # Public state
    # ------------------------------------------------------------------
    @property
    def requirement(self) -> str:
        return self._state.get("requirement", "")

    def output_for(self, agent_type: str) -> Any:
        """Direct read of an agent's stored output. Returns None if missing."""
        return self._state["outputs"].get(agent_type)

    def snapshot(self) -> dict:
        """Return a JSON-serializable copy suitable for Pipeline.context_snapshot."""
        return deepcopy(self._state)

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------
    def save_output(self, agent_type: str, data: Any) -> None:
        """
        Persist an agent's output into the shared snapshot.

        Code reviews and bug fixes accumulate as ordered lists because they
        can run multiple times against different artifacts.
        """
        if agent_type not in ALL_AGENTS:
            raise UnknownAgentError(agent_type)

        if agent_type in LIST_AGENTS:
            self._state["outputs"].setdefault(agent_type, []).append(data)
        else:
            self._state["outputs"][agent_type] = data

    # ------------------------------------------------------------------
    # Slicing — the core behavior
    # ------------------------------------------------------------------
    def get_slice(self, agent_type: str, **kwargs: Any) -> dict:
        """
        Return only the data this agent needs.

        Optional kwargs:
            target_artifact: for code_review / bug_fixer, the agent_type of the
                             artifact under review (e.g. "db_schema").
        """
        if agent_type not in ALL_AGENTS:
            raise UnknownAgentError(agent_type)

        outputs = self._state["outputs"]
        slice_data: dict[str, Any] = {"requirement": self.requirement}

        if agent_type == AGENT_RESEARCH:
            # Just the original requirement.
            pass

        elif agent_type == AGENT_PM:
            self._require(outputs, AGENT_RESEARCH)
            research = outputs[AGENT_RESEARCH]
            slice_data["research"] = {
                "summary": research.get("summary", ""),
                "risks": research.get("risks", []),
                "ambiguities": research.get("ambiguities", []),
            }

        elif agent_type == AGENT_SYSTEM_DESIGNER:
            self._require(outputs, AGENT_PM)
            self._require(outputs, AGENT_RESEARCH)
            pm = outputs[AGENT_PM]
            slice_data["user_stories"] = pm.get("user_stories", [])
            slice_data["scope"] = pm.get("scope", "")
            slice_data["risks"] = outputs[AGENT_RESEARCH].get("risks", [])

        elif agent_type == AGENT_DB_SCHEMA:
            self._require(outputs, AGENT_SYSTEM_DESIGNER)
            slice_data["architecture"] = outputs[AGENT_SYSTEM_DESIGNER]

        elif agent_type == AGENT_API_DESIGNER:
            self._require(outputs, AGENT_DB_SCHEMA)
            slice_data["db_schema"] = outputs[AGENT_DB_SCHEMA]

        elif agent_type == AGENT_CODE_REVIEW:
            target = kwargs.get("target_artifact")
            if target is None:
                raise ValueError("code_review requires target_artifact kwarg")
            self._require(outputs, target)
            slice_data["target_artifact"] = target
            slice_data["artifact"] = outputs[target]

        elif agent_type == AGENT_BUG_FIXER:
            target = kwargs.get("target_artifact")
            if target is None:
                raise ValueError("bug_fixer requires target_artifact kwarg")
            self._require(outputs, target)
            slice_data["target_artifact"] = target
            slice_data["artifact"] = outputs[target]
            reviews = outputs.get(AGENT_CODE_REVIEW, [])
            relevant = [
                r for r in reviews if r.get("target_artifact") == target
            ]
            slice_data["latest_review"] = relevant[-1] if relevant else None

        elif agent_type == AGENT_TESTING:
            self._require(outputs, AGENT_DB_SCHEMA)
            self._require(outputs, AGENT_API_DESIGNER)
            slice_data["db_schema"] = outputs[AGENT_DB_SCHEMA]
            slice_data["api_design"] = outputs[AGENT_API_DESIGNER]

        elif agent_type == AGENT_DOCUMENTATION:
            slice_data["all_outputs"] = deepcopy(outputs)

        return self._guard_size(slice_data)

    # ------------------------------------------------------------------
    # Token guard
    # ------------------------------------------------------------------
    def _guard_size(self, slice_data: dict) -> dict:
        """
        Enforce the per-slice token budget. If over the limit, summarize or
        truncate the largest string-valued nodes until under budget.
        """
        serialized = json.dumps(slice_data, ensure_ascii=False, default=str)
        token_count = _count_tokens(serialized)
        if token_count <= self._max_slice_tokens:
            return slice_data
        return self._compress(slice_data, token_count)

    def _compress(self, slice_data: dict, current_tokens: int) -> dict:
        """
        Reduce slice size by summarizing or truncating big strings. Conservative:
        never silently drops keys, only shortens their content.
        """
        target = self._max_slice_tokens

        def _shorten(text: str, ratio: float) -> str:
            if self._summarizer is not None:
                try:
                    return self._summarizer(text, max(200, int(len(text) * ratio)))
                except Exception:
                    pass
            keep = max(200, int(len(text) * ratio))
            if len(text) <= keep:
                return text
            half = keep // 2
            return text[:half] + "\n…[truncated]…\n" + text[-half:]

        def _walk(node: Any, ratio: float) -> Any:
            if isinstance(node, str):
                if _count_tokens(node) > 200:
                    return _shorten(node, ratio)
                return node
            if isinstance(node, dict):
                return {k: _walk(v, ratio) for k, v in node.items()}
            if isinstance(node, list):
                return [_walk(v, ratio) for v in node]
            return node

        result = slice_data
        for _attempt in range(3):
            ratio = max(0.1, target / max(1, current_tokens))
            result = _walk(result, ratio)
            current_tokens = _count_tokens(
                json.dumps(result, ensure_ascii=False, default=str)
            )
            if current_tokens <= target:
                break
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _require(outputs: dict, agent_type: str) -> None:
        if agent_type not in outputs:
            raise MissingContextError(
                f"missing required predecessor output: {agent_type!r}"
            )
