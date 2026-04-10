"""
Unit tests for the four LLM provider adapters.

No Django, no network — all HTTP calls are mocked via unittest.mock.patch.
Run with:
    python3 -m unittest agents.tests.test_providers -v
"""
import json
import unittest
import urllib.error
from io import BytesIO
from unittest.mock import MagicMock, patch

from provider_settings.providers.anthropic import AnthropicProvider
from provider_settings.providers.base import (
    LLMProvider,
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    ProviderResponse,
    ProviderTimeout,
)
from provider_settings.providers.groq import GroqProvider
from provider_settings.providers.ollama import OllamaProvider
from provider_settings.providers.openrouter import OpenRouterProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_cm(data: dict):
    """
    Build a context-manager mock for urllib.request.urlopen that returns
    the given dict as JSON.
    """
    m = MagicMock()
    m.__enter__ = lambda s: s
    m.__exit__ = MagicMock(return_value=False)
    m.read.return_value = json.dumps(data).encode("utf-8")
    return m


def _http_error(code: int, reason: str = "error") -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url="https://example.com",
        code=code,
        msg=reason,
        hdrs={},  # type: ignore[arg-type]
        fp=BytesIO(b""),
    )


_OPENAI_RESPONSE = {
    "choices": [{"message": {"content": "Hello, world!"}}],
    "usage": {"total_tokens": 42},
}

_OLLAMA_RESPONSE = {
    "message": {"content": "Ciao!"},
    "prompt_eval_count": 10,
    "eval_count": 20,
}

_ANTHROPIC_RESPONSE = {
    "content": [{"type": "text", "text": "Bonjour!"}],
    "usage": {"input_tokens": 5, "output_tokens": 8},
}


# ---------------------------------------------------------------------------
# Groq
# ---------------------------------------------------------------------------
class GroqProviderTests(unittest.TestCase):
    def _provider(self):
        return GroqProvider(api_key="test-key", model="llama-3.3-70b-versatile")

    def test_complete_returns_provider_response(self):
        with patch("urllib.request.urlopen", return_value=_mock_cm(_OPENAI_RESPONSE)):
            resp = self._provider().complete("sys", "user msg")
        self.assertIsInstance(resp, ProviderResponse)
        self.assertEqual(resp.content, "Hello, world!")
        self.assertEqual(resp.provider, "groq")
        self.assertEqual(resp.tokens_used, 42)

    def test_complete_includes_bearer_auth(self):
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["auth"] = req.get_header("Authorization")
            return _mock_cm(_OPENAI_RESPONSE)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            self._provider().complete("", "hi")

        self.assertEqual(captured["auth"], "Bearer test-key")

    def test_complete_omits_empty_system_message(self):
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data.decode())
            return _mock_cm(_OPENAI_RESPONSE)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            self._provider().complete("", "hi")

        roles = [m["role"] for m in captured["body"]["messages"]]
        self.assertNotIn("system", roles)

    def test_complete_includes_system_when_provided(self):
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data.decode())
            return _mock_cm(_OPENAI_RESPONSE)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            self._provider().complete("Be concise.", "hi")

        roles = [m["role"] for m in captured["body"]["messages"]]
        self.assertIn("system", roles)

    def test_complete_raises_auth_error_on_401(self):
        with patch("urllib.request.urlopen", side_effect=_http_error(401, "Unauthorized")):
            with self.assertRaises(ProviderAuthError):
                self._provider().complete("", "hi")

    def test_complete_raises_rate_limit_on_429(self):
        with patch("urllib.request.urlopen", side_effect=_http_error(429, "Too Many")):
            with self.assertRaises(ProviderRateLimitError):
                self._provider().complete("", "hi")

    def test_complete_raises_provider_error_on_500(self):
        with patch("urllib.request.urlopen", side_effect=_http_error(500, "Server Error")):
            with self.assertRaises(ProviderError):
                self._provider().complete("", "hi")

    def test_health_check_returns_true_on_success(self):
        with patch("urllib.request.urlopen", return_value=_mock_cm(_OPENAI_RESPONSE)):
            self.assertTrue(self._provider().health_check())

    def test_health_check_returns_false_on_failure(self):
        with patch("urllib.request.urlopen", side_effect=_http_error(401, "Unauthorized")):
            self.assertFalse(self._provider().health_check())


# ---------------------------------------------------------------------------
# OpenRouter
# ---------------------------------------------------------------------------
class OpenRouterProviderTests(unittest.TestCase):
    def _provider(self):
        return OpenRouterProvider(api_key="or-key", model="meta-llama/llama-3.1-70b")

    def test_complete_returns_content(self):
        with patch("urllib.request.urlopen", return_value=_mock_cm(_OPENAI_RESPONSE)):
            resp = self._provider().complete("sys", "msg")
        self.assertEqual(resp.content, "Hello, world!")
        self.assertEqual(resp.provider, "openrouter")

    def test_complete_posts_to_openrouter_url(self):
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            return _mock_cm(_OPENAI_RESPONSE)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            self._provider().complete("", "hi")

        self.assertIn("openrouter.ai", captured["url"])


# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------
class OllamaProviderTests(unittest.TestCase):
    def _provider(self):
        return OllamaProvider(model="llama3.1")

    def test_complete_returns_content(self):
        with patch("urllib.request.urlopen", return_value=_mock_cm(_OLLAMA_RESPONSE)):
            resp = self._provider().complete("sys", "msg")
        self.assertEqual(resp.content, "Ciao!")
        self.assertEqual(resp.provider, "ollama")
        self.assertEqual(resp.tokens_used, 30)

    def test_complete_uses_stream_false(self):
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data.decode())
            return _mock_cm(_OLLAMA_RESPONSE)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            self._provider().complete("", "hi")

        self.assertFalse(captured["body"]["stream"])

    def test_complete_sends_no_auth_header(self):
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["headers"] = dict(req.headers)
            return _mock_cm(_OLLAMA_RESPONSE)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            self._provider().complete("", "hi")

        self.assertNotIn("Authorization", captured["headers"])

    def test_complete_posts_to_ollama_url(self):
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            return _mock_cm(_OLLAMA_RESPONSE)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            self._provider().complete("", "hi")

        self.assertIn("/api/chat", captured["url"])


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------
class AnthropicProviderTests(unittest.TestCase):
    def _provider(self):
        return AnthropicProvider(api_key="ant-key", model="claude-sonnet-4-6")

    def test_complete_returns_content(self):
        with patch("urllib.request.urlopen", return_value=_mock_cm(_ANTHROPIC_RESPONSE)):
            resp = self._provider().complete("sys", "msg")
        self.assertEqual(resp.content, "Bonjour!")
        self.assertEqual(resp.provider, "anthropic")
        self.assertEqual(resp.tokens_used, 13)

    def test_complete_sends_x_api_key_header(self):
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["headers"] = dict(req.headers)
            return _mock_cm(_ANTHROPIC_RESPONSE)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            self._provider().complete("", "hi")

        self.assertIn("X-api-key", captured["headers"])

    def test_complete_sends_anthropic_version_header(self):
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["headers"] = dict(req.headers)
            return _mock_cm(_ANTHROPIC_RESPONSE)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            self._provider().complete("", "hi")

        self.assertIn("Anthropic-version", captured["headers"])

    def test_system_is_top_level_field(self):
        """Anthropic's API expects system as a top-level field, not inside messages."""
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data.decode())
            return _mock_cm(_ANTHROPIC_RESPONSE)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            self._provider().complete("Be brief.", "hi")

        self.assertIn("system", captured["body"])
        roles = [m["role"] for m in captured["body"]["messages"]]
        self.assertNotIn("system", roles)

    def test_no_system_field_when_system_empty(self):
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data.decode())
            return _mock_cm(_ANTHROPIC_RESPONSE)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            self._provider().complete("", "hi")

        self.assertNotIn("system", captured["body"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
