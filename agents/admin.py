from django.contrib import admin

from .models import AgentTask


@admin.register(AgentTask)
class AgentTaskAdmin(admin.ModelAdmin):
    list_display = (
        "pk",
        "pipeline",
        "agent_type",
        "target_artifact",
        "status",
        "duration_ms",
        "retry_count",
        "provider_used",
        "created_at",
    )
    list_filter = ("agent_type", "status", "provider_used")
    search_fields = ("pipeline__project__requirement",)
    readonly_fields = ("created_at", "finished_at", "duration_ms")
