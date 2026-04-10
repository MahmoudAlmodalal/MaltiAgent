from django.db import models

from agents.context_manager import ALL_AGENTS


class AgentTask(models.Model):
    """
    Represents one agent's execution within a Pipeline.

    `input_slice` stores the context slice produced by ContextManager.get_slice()
    just before the agent ran — this is the key to reproducibility and debugging.
    """

    AGENT_CHOICES = [(a, a) for a in ALL_AGENTS]

    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_DONE = "done"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_RUNNING, "Running"),
        (STATUS_DONE, "Done"),
        (STATUS_FAILED, "Failed"),
    ]

    pipeline = models.ForeignKey(
        "projects.Pipeline",
        on_delete=models.CASCADE,
        related_name="tasks",
    )
    agent_type = models.CharField(max_length=32, choices=AGENT_CHOICES)
    # For code_review / bug_fixer — which artifact is being reviewed.
    target_artifact = models.CharField(max_length=32, blank=True, default="")
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING
    )
    # The slice passed to the agent (persisted for debugging / reproducibility).
    input_slice = models.JSONField(default=dict)
    # The agent's structured output.
    output = models.JSONField(default=dict)
    # Error message if status == failed.
    error = models.TextField(blank=True, default="")
    # Wall-clock time the agent took to run.
    duration_ms = models.PositiveIntegerField(default=0)
    # How many times this task was retried (e.g. after review rejection).
    retry_count = models.PositiveIntegerField(default=0)
    # Which provider actually served this request (filled by BaseAgent).
    provider_used = models.CharField(max_length=32, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["pipeline", "agent_type"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        target = f" → {self.target_artifact}" if self.target_artifact else ""
        return f"AgentTask[{self.agent_type}{target}] pipeline={self.pipeline_id} status={self.status}"
