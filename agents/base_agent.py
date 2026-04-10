"""
BaseAgent — abstract orchestration of one agent's run.

Responsibilities (handled here so subclasses stay tiny):
1. Pull the agent's input slice from ContextManager.
2. Persist a fresh AgentTask row (status=running).
3. Load the system prompt from agents/prompts/{agent_type}.txt.
4. Call the user's ProviderFallbackChain.
5. Parse the JSON response (with fence-stripping).
6. Save the parsed output back into ContextManager.
7. Stamp the AgentTask with status=done, duration_ms, provider_used.
8. On any exception: stamp status=failed + error, leave ContextManager untouched, re-raise.

Subclasses provide:
- `agent_type` (class attribute)
- `_build_user_message(slice_data)` — formats the user prompt from the slice
- (optional) `_parse_response(raw)` — override the default JSON extractor
- (optional) `complete_kwargs()` — override temperature / max_tokens
"""
from __future__ import annotations

import json
import logging
import re
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from django.utils import timezone

from agents.context_manager import ContextManager
from agents.models import AgentTask

if TYPE_CHECKING:
    from projects.models import Pipeline
    from provider_settings.fallback import ProviderFallbackChain

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


class BaseAgent(ABC):
    agent_type: ClassVar[str] = ""
    DEFAULT_TEMPERATURE: ClassVar[float] = 0.2
    DEFAULT_MAX_TOKENS: ClassVar[int] = 4096

    def __init__(
        self,
        pipeline: "Pipeline",
        context_manager: ContextManager,
        provider_chain: "ProviderFallbackChain",
    ):
        if not self.agent_type:
            raise NotImplementedError(
                f"{type(self).__name__} must define class attribute `agent_type`"
            )
        self.pipeline = pipeline
        self.context = context_manager
        self.providers = provider_chain

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def run(self, **slice_kwargs) -> dict:
        """
        Execute the agent end-to-end. Returns the parsed output dict.
        Raises whatever the underlying provider/parser raised on failure.
        """
        # 1. Get the input slice from the context manager.
        slice_data = self.context.get_slice(self.agent_type, **slice_kwargs)

        # 2. Open an AgentTask row in RUNNING state.
        task = AgentTask.objects.create(
            pipeline=self.pipeline,
            agent_type=self.agent_type,
            target_artifact=slice_kwargs.get("target_artifact", ""),
            input_slice=slice_data,
            status=AgentTask.STATUS_RUNNING,
        )

        start = time.monotonic()
        try:
            # 3-5. Build prompt → call providers → parse JSON.
            output, provider_name, tokens = self._execute(slice_data)

            # 6. Persist into the shared context.
            self.context.save_output(self.agent_type, output)

            # 7. Mark the task done.
            duration_ms = int((time.monotonic() - start) * 1000)
            task.status = AgentTask.STATUS_DONE
            task.output = output
            task.provider_used = provider_name
            task.duration_ms = duration_ms
            task.finished_at = timezone.now()
            task.save(
                update_fields=[
                    "status",
                    "output",
                    "provider_used",
                    "duration_ms",
                    "finished_at",
                ]
            )
            return output

        except Exception as exc:
            # 8. Mark the task failed and re-raise.
            duration_ms = int((time.monotonic() - start) * 1000)
            task.status = AgentTask.STATUS_FAILED
            task.error = f"{type(exc).__name__}: {exc}"
            task.duration_ms = duration_ms
            task.finished_at = timezone.now()
            task.save(
                update_fields=["status", "error", "duration_ms", "finished_at"]
            )
            logger.exception("Agent %s failed", self.agent_type)
            raise

    # ------------------------------------------------------------------
    # Provider interaction
    # ------------------------------------------------------------------
    def _execute(self, slice_data: dict) -> tuple[dict, str, int]:
        """
        Build prompt + call providers + parse. Returns (output, provider_name, tokens).
        Separated from run() so tests can patch this in isolation if needed.
        """
        system_prompt = self._load_system_prompt()
        user_message = self._build_user_message(slice_data)

        response, provider_name = self.providers.complete(
            system=system_prompt,
            user=user_message,
            **self.complete_kwargs(),
        )

        parsed = self._parse_response(response.content)
        return parsed, provider_name, response.tokens_used

    # ------------------------------------------------------------------
    # Subclass extension points
    # ------------------------------------------------------------------
    @abstractmethod
    def _build_user_message(self, slice_data: dict) -> str:
        """
        Format the input slice into a user-role message.
        Subclasses typically dump the slice as JSON or as a structured prompt.
        """

    def _parse_response(self, raw: str) -> dict:
        """Default: extract a JSON object from the raw text."""
        return self._extract_json(raw)

    def complete_kwargs(self) -> dict:
        return {
            "temperature": self.DEFAULT_TEMPERATURE,
            "max_tokens": self.DEFAULT_MAX_TOKENS,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _load_system_prompt(self) -> str:
        path = PROMPTS_DIR / f"{self.agent_type}.txt"
        return path.read_text(encoding="utf-8")

    @staticmethod
    def _extract_json(text: str) -> dict:
        """
        Extract a JSON object from a possibly-fenced LLM response.

        Strategy:
        1. Strip ```json ... ``` or ``` ... ``` markdown fences.
        2. json.loads the result.
        3. If that fails, regex-find the first {...} block and try again.
        4. Otherwise raise json.JSONDecodeError.
        """
        text = text.strip()

        # Strip ``` fences if present.
        fence_match = re.match(r"^```(?:[a-zA-Z]+)?\s*\n(.*?)\n```\s*$", text, re.DOTALL)
        if fence_match:
            text = fence_match.group(1).strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Last resort: find the first {...} block (greedy DOTALL).
        obj_match = re.search(r"\{.*\}", text, re.DOTALL)
        if obj_match:
            return json.loads(obj_match.group(0))

        # Trigger a clean JSONDecodeError on the original text.
        return json.loads(text)
