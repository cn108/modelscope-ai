"""Authentication API views (§8 route family: /auth/*).

Thin views; logic in services. Token lifetimes/rotation configured in settings (§11).
"""

from typing import Any, cast

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User
from apps.accounts.services import (
    ChangePasswordSerializer,
    RegisterSerializer,
    UserProfileSerializer,
    UserProfileUpdateSerializer,
    change_password,
    register_user,
    update_profile,
)
from common.audit.models import AuditEvent
from common.audit.serializers import AuditEventSerializer
from common.audit.services import record_event
from common.pagination import DefaultPagination
from common.throttling import LoginRateThrottle


class RegisterView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []

    def post(self, request: Request) -> Response:
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = register_user(**serializer.validated_data)
        except ValueError as exc:
            return Response(
                {"error": {"code": "email_taken", "message": str(exc), "details": None}},
                status=status.HTTP_409_CONFLICT,
            )
        record_event(
            actor=user,
            action="account.created",
            target_type="user",
            target_id=user.pk,
        )
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "user": UserProfileSerializer(user).data,
                # New accounts are immediately authenticated; returning a token
                # pair avoids a second credential round-trip over the wire.
                "tokens": {
                    "access": str(refresh.access_token),
                    "refresh": str(refresh),
                },
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    """Email + password → JWT pair. Uniform error to avoid account enumeration."""

    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_classes = [LoginRateThrottle]

    def post(self, request: Request) -> Response:
        email = str(request.data.get("email", "")).strip().lower()
        password = str(request.data.get("password", ""))
        user = User.objects.filter(email=email).first()
        if user is None or not user.is_active or not user.check_password(password):
            return Response(
                {
                    "error": {
                        "code": "invalid_credentials",
                        "message": "Invalid email or password.",
                        "details": None,
                    }
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        record_event(
            actor=user,
            action="auth.login_succeeded",
            target_type="user",
            target_id=user.pk,
        )
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "user": UserProfileSerializer(user).data,
                "tokens": {"access": str(refresh.access_token), "refresh": str(refresh)},
            }
        )


class RefreshView(APIView):
    """Exchange a (rotated) refresh token for a new access/refresh pair (§11)."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def post(self, request: Request) -> Response:
        serializer = TokenRefreshSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as exc:
            return Response(
                {
                    "error": {
                        "code": "invalid_token",
                        "message": str(exc),
                        "details": None,
                    }
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        return Response(serializer.validated_data)


class LogoutView(APIView):
    """Revoke the caller's refresh token, if supplied.

    The access token remains valid until its short expiry; this endpoint is about
    stopping refresh, not pretending stateless JWTs can be recalled instantly.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        raw = str(request.data.get("refresh", "")).strip()
        if raw:
            try:
                RefreshToken(cast(Any, raw)).blacklist()
            except TokenError:
                # An already-invalid token is not a reason to keep the user signed in.
                pass
        record_event(
            actor=request.user,
            action="auth.logged_out",
            target_type="user",
            target_id=request.user.pk,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response(UserProfileSerializer(request.user).data)

    def patch(self, request: Request) -> Response:
        serializer = UserProfileUpdateSerializer(
            instance=request.user, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        user = update_profile(
            user=request.user, validated_data=serializer.validated_data
        )
        return Response(UserProfileSerializer(user).data)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        revoked = change_password(
            user=request.user,
            current_password=serializer.validated_data["current_password"],
            new_password=serializer.validated_data["new_password"],
        )
        return Response(
            {
                "detail": "Password changed. Other refresh tokens were revoked.",
                "refresh_tokens_revoked": revoked,
            }
        )


class AccountAuditView(APIView):
    """Account-level security events (not scoped to a workspace)."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        events = (
            AuditEvent.objects.filter(actor=request.user, workspace__isnull=True)
            .select_related("actor")
            .order_by("-created_at")
        )
        paginator = DefaultPagination()
        page = paginator.paginate_queryset(events, request, view=self)
        if page is not None:
            return paginator.get_paginated_response(
                AuditEventSerializer(page, many=True).data
            )
        return Response(AuditEventSerializer(events, many=True).data)
