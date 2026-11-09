"""Serializers for project payloads (§8)."""

from rest_framework import serializers

from apps.projects.models import Project


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = [
            "id",
            "workspace",
            "name",
            "description",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ProjectCreateSerializer(serializers.Serializer):
    workspace = serializers.UUIDField()
    name = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True, default="")


class ProjectUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
