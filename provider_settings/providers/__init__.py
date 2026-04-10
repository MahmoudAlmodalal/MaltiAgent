from .anthropic import AnthropicProvider
from .base import (
    LLMProvider,
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    ProviderResponse,
    ProviderTimeout,
)
from .groq import GroqProvider
from .ollama import OllamaProvider
from .openrouter import OpenRouterProvider

ADAPTERS: dict[str, type[LLMProvider]] = {
    "groq": GroqProvider,
    "ollama": OllamaProvider,
    "openrouter": OpenRouterProvider,
    "anthropic": AnthropicProvider,
}

__all__ = [
    "ADAPTERS",
    "LLMProvider",
    "ProviderResponse",
    "ProviderError",
    "ProviderTimeout",
    "ProviderAuthError",
    "ProviderRateLimitError",
    "GroqProvider",
    "OllamaProvider",
    "OpenRouterProvider",
    "AnthropicProvider",
]
