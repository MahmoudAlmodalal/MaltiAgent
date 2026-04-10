"""
Integration tests for the provider_settings DRF API endpoints.

Requires Django + DRF. Run with:
    DJANGO_SETTINGS_MODULE=config.settings_test python3 -m unittest agents.tests.test_provider_api -v
"""
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_test")

import django  # noqa: E402

django.setup()

from django.core.management import call_command  # noqa: E402

call_command("migrate", "--run-syncdb", verbosity=0)

import unittest  # noqa: E402
from unittest.mock import MagicMock, patch  # noqa: E402

from django.contrib.auth import get_user_model  # noqa: E402
from django.test import TestCase  # noqa: E402
from rest_framework.test import APIClient  # noqa: E402

User = get_user_model()


class ProviderConfigAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.alice = User.objects.create_user("alice_api", password="pw")
        self.bob = User.objects.create_user("bob_api", password="pw")
        self.client.force_authenticate(user=self.alice)

    # ----- Create --------------------------------------------------------
    def test_create_provider_config(self):
        resp = self.client.post(
            "/api/provider/config/",
            {
                "provider": "groq",
                "api_key": "gsk-secret",
                "model_name": "llama-3.3-70b-versatile",
                "fallback_order": 1,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["provider"], "groq")
        self.assertEqual(data["fallback_order"], 1)

    def test_api_key_is_not_returned_in_response(self):
        resp = self.client.post(
            "/api/provider/config/",
            {"provider": "groq", "api_key": "super-secret", "model_name": "m"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertNotIn("api_key", resp.json())

    def test_has_api_key_field_is_true_when_key_set(self):
        resp = self.client.post(
            "/api/provider/config/",
            {"provider": "groq", "api_key": "sk-123", "model_name": "m"},
            format="json",
        )
        self.assertTrue(resp.json()["has_api_key"])

    def test_has_api_key_field_is_false_when_key_empty(self):
        resp = self.client.post(
            "/api/provider/config/",
            {"provider": "ollama", "api_key": "", "model_name": "llama3.1"},
            format="json",
        )
        self.assertFalse(resp.json()["has_api_key"])

    # ----- List / isolation -----------------------------------------------
    def test_list_returns_only_current_users_configs(self):
        # Alice creates a config.
        self.client.post(
            "/api/provider/config/",
            {"provider": "groq", "api_key": "alice-key", "model_name": "m"},
            format="json",
        )
        # Bob creates his own config.
        bob_client = APIClient()
        bob_client.force_authenticate(user=self.bob)
        bob_client.post(
            "/api/provider/config/",
            {"provider": "groq", "api_key": "bob-key", "model_name": "m"},
            format="json",
        )

        # Alice should only see her own config.
        resp = self.client.get("/api/provider/config/")
        self.assertEqual(resp.status_code, 200)
        # DRF may return a list or a paginated dict depending on settings.
        body = resp.json()
        results = body["results"] if isinstance(body, dict) else body
        self.assertEqual(len(results), 1)
        # The result must not contain any sensitive key data.
        self.assertNotIn("api_key", results[0])

    def test_unauthenticated_request_is_rejected(self):
        anon = APIClient()
        resp = anon.get("/api/provider/config/")
        self.assertEqual(resp.status_code, 403)


class ProviderTestAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user("tester_api", password="pw")
        self.client.force_authenticate(user=self.user)

    def test_returns_400_for_invalid_provider(self):
        resp = self.client.post(
            "/api/provider/test/",
            {"provider": "invalid_provider"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_returns_503_when_no_config_and_no_settings_default(self):
        # settings_test.py has no PROVIDER_DEFAULTS at all, so the view's
        # `getattr(settings, "PROVIDER_DEFAULTS", {})` returns {} →
        # _resolve_adapter returns None → 503.
        resp = self.client.post(
            "/api/provider/test/", {"provider": "anthropic"}, format="json"
        )
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.json()["status"], "error")

    def test_returns_200_when_health_check_passes(self):
        mock_adapter = MagicMock()
        mock_adapter.health_check.return_value = True

        with patch(
            "provider_settings.views.ProviderTestView._resolve_adapter",
            return_value=mock_adapter,
        ):
            resp = self.client.post(
                "/api/provider/test/", {"provider": "groq"}, format="json"
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ok")

    def test_returns_503_when_health_check_fails(self):
        mock_adapter = MagicMock()
        mock_adapter.health_check.return_value = False

        with patch(
            "provider_settings.views.ProviderTestView._resolve_adapter",
            return_value=mock_adapter,
        ):
            resp = self.client.post(
                "/api/provider/test/", {"provider": "groq"}, format="json"
            )
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.json()["status"], "error")

    def test_uses_saved_config_for_adapter_resolution(self):
        from provider_settings.models import ProviderConfig

        ProviderConfig.objects.create(
            user=self.user,
            provider="groq",
            api_key="my-key",
            model_name="llama-3.3-70b-versatile",
        )

        with patch(
            "provider_settings.providers.groq.GroqProvider.health_check",
            return_value=True,
        ):
            resp = self.client.post(
                "/api/provider/test/", {"provider": "groq"}, format="json"
            )
        self.assertEqual(resp.status_code, 200)

    def test_unauthenticated_test_is_rejected(self):
        anon = APIClient()
        resp = anon.post("/api/provider/test/", {"provider": "groq"}, format="json")
        self.assertEqual(resp.status_code, 403)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
