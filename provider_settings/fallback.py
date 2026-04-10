"""
ProviderFallbackChain — tries providers in fallback_order until one succeeds.

Accepts any object that has the attributes:
    api_key, model_name, base_url, provider, fallback_order
so tests can pass SimpleNamespace / namedtuple without needing the ORM model.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Protocol, runtime_checkable

from provider_settings.providers import ADAPTERS, LLMProvider, ProviderResponse

logger = logging.getLogger(__name__)


@runtime_checkable
class ProviderConfigLike(Protocol):
    """Duck-type protocol satisfied by ProviderConfig (ORM) and test stubs."""

    api_key: str
    model_name: str
    base_url: str
    provider: str
    fallback_order: int


class ProviderChainExhausted(Exception):
    """Raised when every provider in the chain has failed."""

    def __init__(self, errors: list[tuple[str, Exception]]):
        self.errors = errors
        msgs = "; ".join(f"{p}: {e}" for p, e in errors)
        super().__init__(f"All providers exhausted — {msgs}")


class ProviderFallbackChain:
    """
    Iterates over ProviderConfig-like objects sorted by fallback_order (ascending).
    For each config, attempts the completion up to (retries_per_provider + 1) times
    before advancing to the next provider.

    On success: returns (ProviderResponse, provider_name_used).
    On total failure: raises ProviderChainExhausted.
    """

    def __init__(
        self,
        configs: Iterable[ProviderConfigLike],
        retries_per_provider: int = 0,
    ):
        self.configs = sorted(configs, key=lambda c: c.fallback_order)
        self.retries = max(0, retries_per_provider)

    def complete(
        self, system: str, user: str, **kwargs: Any
    ) -> tuple[ProviderResponse, str]:
        errors: list[tuple[str, Exception]] = []
        for cfg in self.configs:
            adapter = self._build_adapter(cfg)
            for attempt in range(self.retries + 1):
                try:
                    resp = adapter.complete(system, user, **kwargs)
                    return resp, cfg.provider
                except Exception as exc:
                    logger.warning(
                        "Provider %s attempt %d/%d failed: %s",
                        cfg.provider,
                        attempt + 1,
                        self.retries + 1,
                        exc,
                    )
                    errors.append((cfg.provider, exc))
        raise ProviderChainExhausted(errors)

    @staticmethod
    def _build_adapter(cfg: ProviderConfigLike) -> LLMProvider:
        cls = ADAPTERS[cfg.provider]
        return cls(
            api_key=cfg.api_key,
            model=cfg.model_name,
            base_url=cfg.base_url,
        )


def build_chain_for_user(user) -> ProviderFallbackChain:
    """
    Construct a ProviderFallbackChain from a user's saved ProviderConfigs,
    ordered by fallback_order ascending.

    Local import of ProviderConfig keeps the rest of the module Django-free
    so unit tests of ProviderFallbackChain itself don't require django.setup().
    """
    from .models import ProviderConfig

    configs = list(ProviderConfig.objects.filter(user=user))
    return ProviderFallbackChain(configs)
