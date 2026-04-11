"""
URL routes for the projects API.

Registered under `/api/projects/` by config.urls.
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ProjectViewSet

router = DefaultRouter()
router.register("", ProjectViewSet, basename="project")

app_name = "projects"

urlpatterns = [
    path("", include(router.urls)),
]
