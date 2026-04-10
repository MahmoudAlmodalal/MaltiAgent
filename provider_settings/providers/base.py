"""
Abstract base for all LLM provider adapters.

All network I/O goes through `_post_json`, which wraps urllib so that:
  - 401/403  → ProviderAuthError
  - 429      → ProviderRateLimitError
  - timeout  → ProviderTimeout
  - other    → ProviderError

Adapters only override `complete()`.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar

logger = logging.getLogger(__name__)


@dataclass
class ProviderResponse:
    content: str
    provider: str
    model: str
    tokens_used: int = 0
    raw: dict | None = field(default=None, repr=False)


class ProviderError(Exception):
    """Base class for all provider failures."""


class ProviderTimeout(ProviderError):
    """Network timeout."""


class ProviderAuthError(ProviderError):
    """Authentication failure (HTTP 401 / 403)."""


class ProviderRateLimitError(ProviderError):
    """Rate limit exceeded (HTTP 429)."""


class LLMProvider(ABC):
    name: ClassVar[str] = ""
    default_base_url: ClassVar[str] = ""

    def __init__(
        self,
        api_key: str = "",
        model: str = "",
        base_url: str = "",
        timeout: int = 60,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url or self.default_base_url
        self.timeout = timeout

    @abstractmethod
    def complete(self, system: str, user: str, **kwargs) -> ProviderResponse:
        """
        Send a chat completion request.
        Raises a ProviderError subclass on failure.
        """

    def health_check(self) -> bool:
        """Return True if the provider is reachable and authenticated."""
        try:
            resp = self.complete(system="", user="ping", max_tokens=8)
            return bool(resp.content)
        except Exception:
            return False

    def _post_json(self, url: str, payload: dict, headers: dict) -> dict:
        """
        POST a JSON payload and return the parsed response dict.
        Maps HTTP / network errors to the Provider* exception hierarchy.
        """
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", **headers},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise ProviderAuthError(f"HTTP {exc.code}: {exc.reason}") from exc
            if exc.code == 429:
                raise ProviderRateLimitError(f"Rate limited (HTTP 429)") from exc
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")[:200]
            except Exception:
                pass
            raise ProviderError(f"HTTP {exc.code}: {exc.reason} — {body}") from exc
        except urllib.error.URLError as exc:
            if "timed out" in str(exc.reason).lower():
                raise ProviderTimeout(str(exc)) from exc
            raise ProviderError(str(exc)) from exc
