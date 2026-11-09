"""Datasets: reusable collections of evaluation test cases (specification M5).

A dataset is versioned by its record content. Every record mutation increments
``Dataset.version`` so an evaluation can state exactly which snapshot it ran
against, and evaluations snapshot the record text into their own result rows.
"""

import uuid

from django.conf import settings
from django.db import models


class Dataset(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="datasets"
    )
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    version = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="datasets",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "datasets_dataset"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "name"], name="uniq_dataset_name_project"
            )
        ]
        indexes = [models.Index(fields=["project", "created_at"])]

    def __str__(self) -> str:
        return f"{self.name} (v{self.version})"


class DatasetRecord(models.Model):
    """One test case: input, optional expected answer and retrieval context."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dataset = models.ForeignKey(
        Dataset, on_delete=models.CASCADE, related_name="records"
    )
    position = models.PositiveIntegerField()
    input = models.TextField()
    expected_output = models.TextField(blank=True)
    context = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "datasets_record"
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(
                fields=["dataset", "position"], name="uniq_dataset_record_position"
            )
        ]

    def __str__(self) -> str:
        return f"{self.dataset.name} #{self.position}"
