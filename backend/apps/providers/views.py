from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.providers.models import ProviderConfig
from apps.providers.serializers import ModelConfigSerializer, ProviderUpdateSerializer
from apps.providers.services import (
    delete_provider,
    get_provider,
    list_provider_models,
    test_provider,
    update_provider,
)
from apps.workspaces.permissions import UUID_RE
from common.throttling import ModelCallRateThrottle


class ProviderViewSet(mixins.RetrieveModelMixin, mixins.UpdateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    lookup_value_regex = UUID_RE
    serializer_class = ProviderUpdateSerializer

    def get_queryset(self):
        return ProviderConfig.objects.filter(
            project__workspace__memberships__user=self.request.user
        ).distinct()

    def retrieve(self, request, *args, **kwargs):
        provider = get_object_or_404(self.get_queryset(), pk=kwargs["pk"])
        # Reuse the role-aware service to preserve the cross-tenant 404 rule.
        provider = get_provider(user=request.user, provider_id=provider.pk)
        return Response(self.get_serializer(provider).data)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        provider = get_provider(user=request.user, provider_id=kwargs["pk"])
        serializer = ProviderUpdateSerializer(instance=provider, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        provider = update_provider(
            actor=request.user,
            provider_id=kwargs["pk"],
            validated_data=serializer.validated_data,
        )
        return Response(self.get_serializer(provider).data)

    def destroy(self, request, *args, **kwargs):
        delete_provider(actor=request.user, provider_id=kwargs["pk"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    def get_throttles(self):
        if self.action in {"test_connection", "models"}:
            return [ModelCallRateThrottle()]
        return super().get_throttles()

    @action(detail=True, methods=["post"], url_path="test")
    def test_connection(self, request, pk=None):
        result = test_provider(actor=request.user, provider_id=pk)
        return Response(result)

    @action(detail=True, methods=["get"], url_path="models")
    def models(self, request, pk=None):
        models = list_provider_models(actor=request.user, provider_id=pk)
        return Response(ModelConfigSerializer(models, many=True).data)
