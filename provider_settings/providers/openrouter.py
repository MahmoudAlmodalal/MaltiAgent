from .base import LLMProvider, ProviderResponse


class OpenRouterProvider(LLMProvider):
    name = "openrouter"
    default_base_url = "https://openrouter.ai/api/v1"

    def complete(self, system: str, user: str, **kwargs) -> ProviderResponse:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.2),
            "max_tokens": kwargs.get("max_tokens", 4096),
        }
        data = self._post_json(
            f"{self.base_url}/chat/completions",
            payload,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        content = data["choices"][0]["message"]["content"]
        tokens = data.get("usage", {}).get("total_tokens", 0)
        return ProviderResponse(
            content=content,
            provider=self.name,
            model=self.model,
            tokens_used=tokens,
            raw=data,
        )
