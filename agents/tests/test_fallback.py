"""
Unit tests for ProviderFallbackChain.

No Django required — uses SimpleNamespace for mock configs and patches ADAPTERS.
Run with:
    python3 -m unittest agents.tests.test_fallback -v
"""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from provider_settings.fallback import ProviderChainExhausted, ProviderFallbackChain
from provider_settings.providers.base import ProviderResponse


def _cfg(provider: str, order: int, api_key: str = "k") -> SimpleNamespace:
    return SimpleNamespace(
        provider=provider,
        fallback_order=order,
        api_key=api_key,
        model_name="test-model",
        base_url="",
    )


def _ok_response(provider: str = "groq") -> ProviderResponse:
    return ProviderResponse(content="OK", provider=provider, model="test-model")


def _mock_adapter_cls(response=None, raises=None):
    """Return a mock provider class whose complete() either returns or raises."""
    cls = MagicMock()
    instance = MagicMock()
    cls.return_value = instance
    if raises is not None:
        instance.complete.side_effect = raises
    else:
        instance.complete.return_value = response
    return cls


FAKE_ADAPTERS = {
    "groq": _mock_adapter_cls,
    "ollama": _mock_adapter_cls,
    "openrouter": _mock_adapter_cls,
    "anthropic": _mock_adapter_cls,
}


class FallbackChainTests(unittest.TestCase):
    def test_first_provider_succeeds(self):
        groq_cls = _mock_adapter_cls(response=_ok_response("groq"))
        ollama_cls = _mock_adapter_cls(response=_ok_response("ollama"))
        adapters = {"groq": groq_cls, "ollama": ollama_cls}

        with patch("provider_settings.fallback.ADAPTERS", adapters):
            chain = ProviderFallbackChain(
                [_cfg("groq", 1), _cfg("ollama", 2)]
            )
            resp, used = chain.complete("sys", "user")

        self.assertEqual(resp.content, "OK")
        self.assertEqual(used, "groq")
        # Second provider must never be called.
        ollama_cls.return_value.complete.assert_not_called()

    def test_falls_through_to_second_on_failure(self):
        groq_cls = _mock_adapter_cls(raises=RuntimeError("groq down"))
        ollama_cls = _mock_adapter_cls(response=_ok_response("ollama"))
        adapters = {"groq": groq_cls, "ollama": ollama_cls}

        with patch("provider_settings.fallback.ADAPTERS", adapters):
            chain = ProviderFallbackChain(
                [_cfg("groq", 1), _cfg("ollama", 2)]
            )
            resp, used = chain.complete("sys", "user")

        self.assertEqual(used, "ollama")
        self.assertEqual(resp.content, "OK")

    def test_exhausted_raises_when_all_fail(self):
        groq_cls = _mock_adapter_cls(raises=RuntimeError("fail"))
        ollama_cls = _mock_adapter_cls(raises=RuntimeError("also fail"))
        adapters = {"groq": groq_cls, "ollama": ollama_cls}

        with patch("provider_settings.fallback.ADAPTERS", adapters):
            chain = ProviderFallbackChain(
                [_cfg("groq", 1), _cfg("ollama", 2)]
            )
            with self.assertRaises(ProviderChainExhausted) as ctx:
                chain.complete("sys", "user")

        errors = ctx.exception.errors
        self.assertEqual(len(errors), 2)
        providers_tried = [p for p, _ in errors]
        self.assertIn("groq", providers_tried)
        self.assertIn("ollama", providers_tried)

    def test_fallback_order_respected(self):
        call_order = []

        def make_cls(name):
            cls = MagicMock()
            instance = MagicMock()
            cls.return_value = instance

            def complete(system, user, **kwargs):
                call_order.append(name)
                raise RuntimeError(f"{name} fail")

            instance.complete.side_effect = complete
            return cls

        adapters = {
            "groq": make_cls("groq"),
            "ollama": make_cls("ollama"),
            "openrouter": make_cls("openrouter"),
        }

        with patch("provider_settings.fallback.ADAPTERS", adapters):
            chain = ProviderFallbackChain([
                _cfg("openrouter", 3),
                _cfg("groq", 1),
                _cfg("ollama", 2),
            ])
            with self.assertRaises(ProviderChainExhausted):
                chain.complete("", "")

        self.assertEqual(call_order, ["groq", "ollama", "openrouter"])

    def test_retries_per_provider(self):
        """With retries=2, each provider is tried 3 times before advancing."""
        call_counts = {"groq": 0, "ollama": 0}

        def make_failing_cls(name):
            cls = MagicMock()
            instance = MagicMock()
            cls.return_value = instance

            def complete(system, user, **kwargs):
                call_counts[name] += 1
                raise RuntimeError("fail")

            instance.complete.side_effect = complete
            return cls

        adapters = {
            "groq": make_failing_cls("groq"),
            "ollama": make_failing_cls("ollama"),
        }
        with patch("provider_settings.fallback.ADAPTERS", adapters):
            chain = ProviderFallbackChain(
                [_cfg("groq", 1), _cfg("ollama", 2)],
                retries_per_provider=2,
            )
            with self.assertRaises(ProviderChainExhausted):
                chain.complete("", "")

        # retries=2 means 3 attempts (1 + 2 retries)
        self.assertEqual(call_counts["groq"], 3)
        self.assertEqual(call_counts["ollama"], 3)

    def test_second_provider_not_retried_if_first_succeeds_on_retry(self):
        call_counts = {"groq": 0}

        def make_cls_succeeds_on_second(name):
            cls = MagicMock()
            instance = MagicMock()
            cls.return_value = instance
            attempt = [0]

            def complete(system, user, **kwargs):
                attempt[0] += 1
                call_counts[name] = attempt[0]
                if attempt[0] == 1:
                    raise RuntimeError("first attempt fails")
                return _ok_response(name)

            instance.complete.side_effect = complete
            return cls

        ollama_cls = _mock_adapter_cls(response=_ok_response("ollama"))
        adapters = {
            "groq": make_cls_succeeds_on_second("groq"),
            "ollama": ollama_cls,
        }

        with patch("provider_settings.fallback.ADAPTERS", adapters):
            chain = ProviderFallbackChain(
                [_cfg("groq", 1), _cfg("ollama", 2)],
                retries_per_provider=1,
            )
            resp, used = chain.complete("", "")

        self.assertEqual(used, "groq")
        self.assertEqual(call_counts["groq"], 2)
        ollama_cls.return_value.complete.assert_not_called()

    def test_chain_exhausted_contains_all_errors(self):
        error_a = ValueError("value error")
        error_b = RuntimeError("runtime error")

        adapters = {
            "groq": _mock_adapter_cls(raises=error_a),
            "ollama": _mock_adapter_cls(raises=error_b),
        }

        with patch("provider_settings.fallback.ADAPTERS", adapters):
            chain = ProviderFallbackChain(
                [_cfg("groq", 1), _cfg("ollama", 2)]
            )
            with self.assertRaises(ProviderChainExhausted) as ctx:
                chain.complete("", "")

        error_map = {p: e for p, e in ctx.exception.errors}
        self.assertIs(error_map["groq"], error_a)
        self.assertIs(error_map["ollama"], error_b)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
