"""Evaluation API: create, monitor, inspect per-case results, rerun."""

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.evaluations.models import Evaluation, EvaluationResult, EvaluationReview
from apps.evaluations.serializers import (
    EvaluationResultSerializer,
    EvaluationReviewInputSerializer,
    EvaluationReviewSerializer,
    EvaluationSerializer,
)
from apps.evaluations.services import (
    enqueue_evaluation,
    evaluation_detail,
    evaluation_for_user,
    rerun_evaluation,
)
from apps.workspaces.models import Membership
from apps.workspaces.permissions import UUID_RE
from common.throttling import ModelCallRateThrottle
from integrations.evaluation.registry import catalog


class EvaluationViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    lookup_value_regex = UUID_RE
    serializer_class = EvaluationSerializer

    def get_queryset(self):
        return Evaluation.objects.filter(
            project__workspace__memberships__user=self.request.user
        ).distinct()

    def get_throttles(self):
        if self.action == "rerun":
            return [ModelCallRateThrottle()]
        return super().get_throttles()

    def retrieve(self, request, *args, **kwargs):
        evaluation = evaluation_detail(user=request.user, evaluation_id=kwargs["pk"])
        return Response(EvaluationSerializer(evaluation).data)

    @action(detail=True, methods=["get"], url_path="results")
    def results(self, request, pk=None):
        evaluation = evaluation_for_user(request.user, pk)
        rows = (
            EvaluationResult.objects.filter(evaluation=evaluation)
            .select_related("model")
            .prefetch_related("reviews__reviewer")
            .order_by("model__position", "record_position")
        )
        model_id = request.query_params.get("model")
        if model_id:
            rows = rows.filter(model_id=model_id)
        row_status = request.query_params.get("status")
        if row_status in {"pending", "succeeded", "failed"}:
            rows = rows.filter(status=row_status)

        page = self.paginate_queryset(rows)
        if page is not None:
            return self.get_paginated_response(
                EvaluationResultSerializer(page, many=True).data
            )
        return Response(EvaluationResultSerializer(rows, many=True).data)

    @action(detail=True, methods=["post"], url_path="rerun")
    def rerun(self, request, pk=None):
        evaluation = rerun_evaluation(actor=request.user, evaluation_id=pk)
        evaluation = enqueue_evaluation(evaluation)
        evaluation = evaluation_detail(user=request.user, evaluation_id=evaluation.pk)
        return Response(
            EvaluationSerializer(evaluation).data, status=status.HTTP_201_CREATED
        )


class EvaluationResultReviewView(APIView):
    """Human annotations for a sampled result; one row per reviewer."""

    permission_classes = [IsAuthenticated]

    def _result(self, request, evaluation_id, result_id, minimum_role):
        evaluation = evaluation_for_user(
            request.user, evaluation_id, minimum_role=minimum_role
        )
        result = EvaluationResult.objects.filter(
            evaluation=evaluation, pk=result_id
        ).first()
        if result is None:
            from rest_framework.exceptions import NotFound

            raise NotFound("Evaluation result not found.")
        return result

    def get(self, request, evaluation_id, result_id):
        result = self._result(
            request, evaluation_id, result_id, Membership.Role.VIEWER
        )
        reviews = result.reviews.select_related("reviewer").all()
        return Response(EvaluationReviewSerializer(reviews, many=True).data)

    def post(self, request, evaluation_id, result_id):
        result = self._result(
            request, evaluation_id, result_id, Membership.Role.MEMBER
        )
        serializer = EvaluationReviewInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        review, _ = EvaluationReview.objects.update_or_create(
            result=result,
            reviewer=request.user,
            defaults=serializer.validated_data,
        )
        return Response(
            EvaluationReviewSerializer(review).data, status=status.HTTP_200_OK
        )


class EvaluationMetricCatalogView(APIView):
    """List the metrics the platform can actually compute right now."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"metrics": catalog()})
