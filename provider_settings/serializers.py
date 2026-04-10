from rest_framework import serializers

from .models import ProviderConfig


class ProviderConfigSerializer(serializers.ModelSerializer):
    # Computed field: never returns the key itself, just whether one is set.
    has_api_key = serializers.SerializerMethodField()

    class Meta:
        model = ProviderConfig
        fields = [
            "id",
            "provider",
            "api_key",
            "has_api_key",
            "model_name",
            "base_url",
            "is_default",
            "fallback_order",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
        extra_kwargs = {
            # api_key is write-only: never serialized on read.
            "api_key": {"write_only": True, "required": False, "allow_blank": True},
        }

    def get_has_api_key(self, obj: ProviderConfig) -> bool:
        return bool(obj.api_key)
