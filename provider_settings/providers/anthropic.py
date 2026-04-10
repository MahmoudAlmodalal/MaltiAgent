from .base import LLMProvider, ProviderResponse

ANTHROPIC_API_VERSION = "2023-06-01"


class AnthropicProvider(LLMProvider):
    """
    Adapter for the Anthropic Messages API.

    Note: Anthropic's payload shape differs from OpenAI-compatible APIs —
    `system` is a top-level field, not a message in the messages array.
    """

    name = "anthropic"
    default_base_url = "https://api.anthropic.com"

    def complete(self, system: str, user: str, **kwargs) -> ProviderResponse:
        payload: dict = {
            "model": self.model,
            "max_tokens": kwargs.get("max_tokens", 4096),
            "messages": [{"role": "user", "content": user}],
        }
        if system:
            payload["system"] = system

        data = self._post_json(
            f"{self.base_url}/v1/messages",
            payload,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": ANTHROPIC_API_VERSION,
            },
        )
        content = data["content"][0]["text"]
        usage = data.get("usage", {})
        tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
        return ProviderResponse(
            content=content,
            provider=self.name,
            model=self.model,
            tokens_used=tokens,
            raw=data,
        )
