from __future__ import annotations

import logging

from rest_framework import serializers as drf_serializers
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ProviderConfig
from .providers import ADAPTERS, LLMProvider
from .serializers import ProviderConfigSerializer

logger = logging.getLogger(__name__)


class ProviderConfigViewSet(viewsets.ModelViewSet):
    """
    CRUD for the current user's LLM provider configurations.

    GET  /api/provider/config/        → list
    POST /api/provider/config/        → create
    GET  /api/provider/config/{id}/   → retrieve
    PUT  /api/provider/config/{id}/   → update
    DEL  /api/provider/config/{id}/   → delete
    """

    serializer_class = ProviderConfigSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Users only see their own configurations.
        return ProviderConfig.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class ProviderTestView(APIView):
    """
    POST /api/provider/test/

    Body:    {"provider": "groq"}

    Tests whether a provider is reachable and authenticated by calling
    its health_check(). Resolves the adapter in this order:
      1. The user's saved ProviderConfig for that provider
      2. settings.PROVIDER_DEFAULTS[provider] (dev fallback)

    Responses:
      200  {"status": "ok",    "provider": "groq"}
      503  {"status": "error", "provider": "groq", "message": "..."}
      400  validation error (unknown provider etc.)
    """

    permission_classes = [IsAuthenticated]

    class _BodySerializer(drf_serializers.Serializer):
        provider = drf_serializers.ChoiceField(
            choices=list(ADAPTERS.keys()), required=True
        )

    def post(self, request: Request) -> Response:
        body = self._BodySerializer(data=request.data)
        if not body.is_valid():
            return Response(body.errors, status=status.HTTP_400_BAD_REQUEST)

        provider_name: str = body.validated_data["provider"]
        adapter = self._resolve_adapter(request.user, provider_name)

        if adapter is None:
            return Response(
                {
                    "status": "error",
                    "provider": provider_name,
                    "message": "No configuration found for this provider.",
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        ok = adapter.health_check()
        if ok:
            return Response({"status": "ok", "provider": provider_name})
        return Response(
            {
                "status": "error",
                "provider": provider_name,
                "message": "Provider health check failed.",
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    @staticmethod
    def _resolve_adapter(user, provider_name: str) -> LLMProvider | None:
        from django.conf import settings

        # 1. User's saved config.
        try:
            cfg = ProviderConfig.objects.get(user=user, provider=provider_name)
            cls = ADAPTERS[provider_name]
            return cls(
                api_key=cfg.api_key,
                model=cfg.model_name,
                base_url=cfg.base_url,
            )
        except ProviderConfig.DoesNotExist:
            pass

        # 2. Settings defaults (for development without a saved config).
        defaults = getattr(settings, "PROVIDER_DEFAULTS", {}).get(provider_name, {})
        model = defaults.get("model", "")
        if not model:
            return None
        cls = ADAPTERS[provider_name]
        return cls(
            api_key=defaults.get("api_key", ""),
            model=model,
            base_url=defaults.get("host", ""),
        )
