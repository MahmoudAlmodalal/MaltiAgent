from django.conf import settings
from django.db import models

from .fields import EncryptedTextField


class ProviderConfig(models.Model):
    PROVIDER_CHOICES = [
        ("groq", "Groq"),
        ("ollama", "Ollama"),
        ("openrouter", "OpenRouter"),
        ("anthropic", "Anthropic"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="provider_configs",
    )
    provider = models.CharField(max_length=32, choices=PROVIDER_CHOICES)
    # Stored encrypted at rest.
    api_key = EncryptedTextField(blank=True, default="")
    model_name = models.CharField(max_length=128)
    # Base URL for self-hosted providers (e.g. Ollama) or OpenRouter overrides.
    base_url = models.CharField(max_length=255, blank=True, default="")
    is_default = models.BooleanField(default=False)
    # Lower numbers are tried first in the fallback chain.
    fallback_order = models.PositiveIntegerField(default=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["fallback_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "provider"],
                name="unique_user_provider",
            )
        ]

    def __str__(self) -> str:
        return f"{self.user} / {self.provider} (order={self.fallback_order})"
