from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ProviderConfigViewSet, ProviderTestView

router = DefaultRouter()
router.register("config", ProviderConfigViewSet, basename="provider-config")

app_name = "provider_settings"

urlpatterns = [
    path("", include(router.urls)),
    path("test/", ProviderTestView.as_view(), name="test"),
]
