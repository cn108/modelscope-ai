"""Project-scoped provider configuration and encrypted credential material."""

import uuid

from django.db import models


class ProviderConfig(models.Model):
    class Kind(models.TextChoices):
        ZAI = "zai", "Z.ai"
        OLLAMA = "ollama", "Ollama"
        LMSTUDIO = "lmstudio", "LM Studio"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="providers"
    )
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    endpoint = models.URLField(max_length=500, blank=True)
    settings = models.JSONField(default=dict, blank=True)
    connection_status = models.CharField(max_length=16, default="untested")
    connection_detail = models.CharField(max_length=240, blank=True)
    last_tested_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "providers_provider_config"
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "name"], name="uniq_provider_name_project"
            )
        ]
        indexes = [models.Index(fields=["project", "kind"])]

    def __str__(self) -> str:
        return f"{self.name} ({self.kind})"


class ProviderSecret(models.Model):
    """Encrypted provider secret, intentionally separate from config JSON."""

    provider = models.OneToOneField(
        ProviderConfig, on_delete=models.CASCADE, related_name="secret"
    )
    encrypted_value = models.BinaryField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "providers_provider_secret"


class ModelConfig(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.ForeignKey(
        ProviderConfig, on_delete=models.CASCADE, related_name="models"
    )
    model_id = models.CharField(max_length=200)
    display_name = models.CharField(max_length=200, blank=True)
    defaults = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "providers_model_config"
        ordering = ["model_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "model_id"], name="uniq_model_id_provider"
            )
        ]

    def __str__(self) -> str:
        return f"{self.provider.name}: {self.model_id}"
