from django.apps import AppConfig


class AgentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "agents"

    def ready(self):
        # Import signal handlers so they get registered.
        from . import signals  # noqa: F401
