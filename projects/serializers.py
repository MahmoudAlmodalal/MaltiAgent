from rest_framework import serializers

from agents.models import AgentTask

from .models import FinalOutput, Pipeline, Project


class AgentTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentTask
        fields = [
            "id",
            "agent_type",
            "target_artifact",
            "status",
            "input_slice",
            "output",
            "error",
            "duration_ms",
            "retry_count",
            "provider_used",
            "created_at",
            "finished_at",
        ]
        read_only_fields = fields


class PipelineSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pipeline
        fields = [
            "id",
            "execution_plan",
            "current_step",
            "started_at",
            "finished_at",
        ]
        read_only_fields = fields


class ProjectSerializer(serializers.ModelSerializer):
    """Summary serializer used by list / create / retrieve."""

    pipeline = PipelineSerializer(read_only=True)

    class Meta:
        model = Project
        fields = [
            "id",
            "requirement",
            "status",
            "created_at",
            "updated_at",
            "pipeline",
        ]
        read_only_fields = ["id", "status", "created_at", "updated_at", "pipeline"]


class FinalOutputSerializer(serializers.ModelSerializer):
    class Meta:
        model = FinalOutput
        fields = ["id", "full_report", "per_agent_outputs", "created_at"]
        read_only_fields = fields
