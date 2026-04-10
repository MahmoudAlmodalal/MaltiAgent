from django.contrib import admin

from .models import ProviderConfig


@admin.register(ProviderConfig)
class ProviderConfigAdmin(admin.ModelAdmin):
    list_display = ("user", "provider", "model_name", "is_default", "fallback_order", "updated_at")
    list_filter = ("provider", "is_default")
    search_fields = ("user__username", "provider", "model_name")
    ordering = ("user", "fallback_order")
    # Never expose the encrypted api_key in list views.
    readonly_fields = ("created_at", "updated_at")
    # Exclude api_key from the list — only show in detail form.
    fields = (
        "user",
        "provider",
        "api_key",
        "model_name",
        "base_url",
        "is_default",
        "fallback_order",
        "created_at",
        "updated_at",
    )
