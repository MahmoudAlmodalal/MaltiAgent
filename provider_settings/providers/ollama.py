from .base import LLMProvider, ProviderResponse


class OllamaProvider(LLMProvider):
    """
    Adapter for a local Ollama instance.
    No API key required — set base_url if running on a non-default host.
    """

    name = "ollama"
    default_base_url = "http://localhost:11434"

    def complete(self, system: str, user: str, **kwargs) -> ProviderResponse:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": kwargs.get("temperature", 0.2),
                "num_predict": kwargs.get("max_tokens", 4096),
            },
        }
        data = self._post_json(
            f"{self.base_url}/api/chat",
            payload,
            headers={},  # Ollama does not require auth
        )
        content = data["message"]["content"]
        # Ollama reports token counts under different keys.
        tokens = data.get("prompt_eval_count", 0) + data.get("eval_count", 0)
        return ProviderResponse(
            content=content,
            provider=self.name,
            model=self.model,
            tokens_used=tokens,
            raw=data,
        )
