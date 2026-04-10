"""
Agent Runner — wires Pipeline state, ContextManager, and ProviderFallbackChain.

This is the integration point that Phase 7's Celery tasks call. Pulled out of
base_agent.py so the abstract class itself stays free of pipeline-loading logic
and is easier to unit-test in isolation.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from agents.context_manager import ContextManager
from provider_settings.fallback import build_chain_for_user

if TYPE_CHECKING:
    from agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


def run_agent(
    pipeline_id: int,
    agent_class: "type[BaseAgent]",
    **slice_kwargs,
) -> dict:
    """
    Load Pipeline state, build ContextManager + ProviderFallbackChain,
    execute the agent, persist the updated snapshot, and return the agent output.

    Steps:
    1. Fetch the Pipeline (with related project + user).
    2. Rehydrate ContextManager from `pipeline.context_snapshot`.
    3. Wire a summarizer that uses the user's provider chain
       (low temperature, short max_tokens) so the ContextManager can
       compress oversized slices.
    4. Run the agent.
    5. Save the new snapshot back to the Pipeline + update current_step.
    """
    from projects.models import Pipeline

    pipeline = Pipeline.objects.select_related("project", "project__created_by").get(
        pk=pipeline_id
    )
    user = pipeline.project.created_by

    chain = build_chain_for_user(user)

    def _summarizer(text: str, target_chars: int) -> str:
        """Use the provider chain to summarize text down to ~target_chars."""
        try:
            response, _ = chain.complete(
                system=(
                    "You are a summarizer. Compress the following text to under "
                    f"{max(50, target_chars // 4)} tokens while preserving key facts, "
                    "decisions, and identifiers. Return only the summary."
                ),
                user=text,
                temperature=0.0,
                max_tokens=max(64, target_chars // 4),
            )
            return response.content
        except Exception as exc:
            logger.warning("Summarizer failed, falling back to truncation: %s", exc)
            # Let ContextManager fall back to head+tail truncation by re-raising.
            raise

    context = ContextManager(
        snapshot=pipeline.context_snapshot,
        summarizer=_summarizer,
    )

    agent = agent_class(
        pipeline=pipeline,
        context_manager=context,
        provider_chain=chain,
    )

    output = agent.run(**slice_kwargs)

    # Persist the updated snapshot + advance current_step.
    pipeline.context_snapshot = context.snapshot()
    pipeline.current_step = agent_class.agent_type
    pipeline.save(update_fields=["context_snapshot", "current_step"])

    return output
