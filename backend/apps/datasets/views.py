"""Dataset and dataset-record API endpoints."""

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.datasets.importers import DatasetImportError
from apps.datasets.models import Dataset, DatasetRecord
from apps.datasets.serializers import (
    DatasetCreateSerializer,
    DatasetImportSerializer,
    DatasetRecordInputSerializer,
    DatasetRecordSerializer,
    DatasetRecordUpdateSerializer,
    DatasetSerializer,
    DatasetUpdateSerializer,
)
from apps.datasets.services import (
    create_dataset,
    create_record,
    dataset_for_user,
    dataset_record_for_user,
    delete_dataset,
    delete_record,
    get_dataset,
    import_records,
    list_datasets,
    list_records,
    update_dataset,
    update_record,
)
from apps.workspaces.permissions import UUID_RE


class DatasetViewSet(
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    lookup_value_regex = UUID_RE
    serializer_class = DatasetSerializer

    def get_queryset(self):
        return Dataset.objects.filter(
            project__workspace__memberships__user=self.request.user
        ).distinct()

    def retrieve(self, request, *args, **kwargs):
        dataset = get_dataset(user=request.user, dataset_id=kwargs["pk"])
        return Response(DatasetSerializer(dataset).data)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        dataset = dataset_for_user(request.user, kwargs["pk"])
        serializer = DatasetUpdateSerializer(data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        dataset = update_dataset(
            actor=request.user,
            dataset_id=dataset.pk,
            validated_data=serializer.validated_data,
        )
        return Response(DatasetSerializer(dataset).data)

    def destroy(self, request, *args, **kwargs):
        delete_dataset(actor=request.user, dataset_id=kwargs["pk"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get", "post"], url_path="records")
    def records(self, request, pk=None):
        dataset = dataset_for_user(request.user, pk)
        if request.method == "POST":
            serializer = DatasetRecordInputSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            record = create_record(
                actor=request.user,
                dataset_id=dataset.pk,
                validated_data=serializer.validated_data,
            )
            return Response(
                DatasetRecordSerializer(record).data, status=status.HTTP_201_CREATED
            )

        rows = list_records(user=request.user, dataset_id=dataset.pk)
        page = self.paginate_queryset(rows)
        if page is not None:
            return self.get_paginated_response(DatasetRecordSerializer(page, many=True).data)
        return Response(DatasetRecordSerializer(rows, many=True).data)

    @action(detail=True, methods=["post"], url_path="import")
    def import_file(self, request, pk=None):
        dataset = dataset_for_user(request.user, pk)
        serializer = DatasetImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        upload = serializer.validated_data["file"]
        try:
            result = import_records(
                actor=request.user,
                dataset_id=dataset.pk,
                filename=upload.name,
                raw=upload.read(),
                mode=serializer.validated_data["mode"],
            )
        except DatasetImportError as exc:
            # Returned directly (not via DRF's ValidationError) so row numbers
            # and counts keep their JSON types instead of becoming strings.
            return Response(
                {
                    "error": {
                        "code": "invalid_dataset",
                        "message": "The dataset file could not be imported.",
                        "details": {
                            "errors": exc.errors,
                            "error_count": exc.error_count,
                        },
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(result, status=status.HTTP_201_CREATED)


class DatasetRecordViewSet(
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    lookup_value_regex = UUID_RE
    serializer_class = DatasetRecordSerializer

    def get_queryset(self):
        return DatasetRecord.objects.filter(
            dataset__project__workspace__memberships__user=self.request.user
        ).distinct()

    def retrieve(self, request, *args, **kwargs):
        record = dataset_record_for_user(request.user, kwargs["pk"])
        return Response(DatasetRecordSerializer(record).data)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        dataset_record_for_user(request.user, kwargs["pk"])
        serializer = DatasetRecordUpdateSerializer(data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        record = update_record(
            actor=request.user,
            record_id=kwargs["pk"],
            validated_data=serializer.validated_data,
        )
        return Response(DatasetRecordSerializer(record).data)

    def destroy(self, request, *args, **kwargs):
        delete_record(actor=request.user, record_id=kwargs["pk"])
        return Response(status=status.HTTP_204_NO_CONTENT)


def project_datasets(*, user, project):
    """List datasets for a project (used by the project detail action)."""
    return list_datasets(user=user, project_id=project.pk)


def project_create_dataset(*, user, project, data):
    serializer = DatasetCreateSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    return create_dataset(
        actor=user, project_id=project.pk, validated_data=serializer.validated_data
    )
