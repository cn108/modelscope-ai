"""Saved prompts with append-only version history (specification M4).

A saved prompt is a mutable container; its contents live in immutable
``PromptVersion`` rows. Editing a prompt never rewrites history, and executions
copy the prompt text they used so later edits cannot change old experiments.
"""

import uuid

from django.conf import settings
from django.db import models


class Prompt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="prompts"
    )
    name = models.CharField(max_length=160)
    description = models.CharField(max_length=400, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_prompts",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "prompts_prompt"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "name"], name="uniq_prompt_name_project"
            )
        ]
        indexes = [models.Index(fields=["project", "updated_at"])]

    def __str__(self) -> str:
        return self.name


class PromptVersion(models.Model):
    """Immutable content snapshot; rows are only ever appended."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    prompt = models.ForeignKey(Prompt, on_delete=models.CASCADE, related_name="versions")
    version_number = models.PositiveIntegerField()
    system_prompt = models.TextField(blank=True)
    user_prompt = models.TextField()
    parameters = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_prompt_versions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "prompts_prompt_version"
        ordering = ["-version_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["prompt", "version_number"], name="uniq_prompt_version_number"
            )
        ]

    def __str__(self) -> str:
        return f"{self.prompt.name} v{self.version_number}"
