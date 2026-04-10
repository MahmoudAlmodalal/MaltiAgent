from django.contrib import admin

from .models import FinalOutput, Pipeline, Project


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("pk", "short_requirement", "status", "created_by", "created_at")
    list_filter = ("status",)
    search_fields = ("requirement", "created_by__username")
    readonly_fields = ("created_at", "updated_at")

    @admin.display(description="Requirement")
    def short_requirement(self, obj: Project) -> str:
        return obj.requirement[:80] + "…" if len(obj.requirement) > 80 else obj.requirement


@admin.register(Pipeline)
class PipelineAdmin(admin.ModelAdmin):
    list_display = ("pk", "project", "current_step", "started_at", "finished_at")
    list_filter = ("current_step",)
    readonly_fields = ("started_at", "finished_at")


@admin.register(FinalOutput)
class FinalOutputAdmin(admin.ModelAdmin):
    list_display = ("pk", "project", "created_at")
    readonly_fields = ("created_at",)
