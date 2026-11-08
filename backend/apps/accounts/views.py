"""Authentication API views (§8 route family: /auth/*).

Thin views; logic in services. Token lifetimes/rotation configured in settings (§11).
"""

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User
from apps.accounts.services import (
    RegisterSerializer,
    UserProfileSerializer,
    register_user,
)


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
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response(UserProfileSerializer(request.user).data)
