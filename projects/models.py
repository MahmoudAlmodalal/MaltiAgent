from django.conf import settings
from django.db import models


class Project(models.Model):
    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_RUNNING, "Running"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
    ]

    requirement = models.TextField()
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING
    )
    # Nullable so anonymous/system-created projects are possible.
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="projects",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        short = self.requirement[:60] + "…" if len(self.requirement) > 60 else self.requirement
        return f"[{self.pk}] {short} ({self.status})"


class Pipeline(models.Model):
    """One pipeline per project — tracks execution state and shared context."""

    project = models.OneToOneField(
        Project, on_delete=models.CASCADE, related_name="pipeline"
    )
    # JSON produced by the Orchestrator describing ordered steps + dependencies.
    execution_plan = models.JSONField(default=dict)
    # Name of the agent currently running (or last ran).
    current_step = models.CharField(max_length=64, blank=True, default="")
    # Serialized ContextManager.snapshot() — updated after each agent completes.
    context_snapshot = models.JSONField(default=dict)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"Pipeline for Project #{self.project_id} [{self.current_step or 'not started'}]"


class FinalOutput(models.Model):
    """Consolidated report produced by the Documentation agent."""

    project = models.OneToOneField(
        Project, on_delete=models.CASCADE, related_name="final_output"
    )
    # Full Markdown report.
    full_report = models.TextField(blank=True, default="")
    # Individual outputs keyed by agent_type for programmatic access.
    per_agent_outputs = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"FinalOutput for Project #{self.project_id}"
