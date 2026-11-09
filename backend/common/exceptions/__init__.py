"""Consistent API error shape (specification section 8)."""

from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler


class ServiceUnavailable(APIException):
    """HTTP 503 when a server-side dependency or configuration is missing."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "The service is temporarily unavailable."
    default_code = "service_unavailable"


class Conflict(APIException):
    """HTTP 409 for uniqueness conflicts that are not validation errors."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "Resource already exists."
    default_code = "conflict"


def api_exception_handler(exc, context):
    """Wrap DRF errors in a stable envelope: {error: {code, message, details}}."""
    response = exception_handler(exc, context)
    if response is None:
        return None
    data = response.data
    code = getattr(exc, "default_code", "error")
    message = getattr(exc, "default_detail", "An error occurred.")
    if isinstance(data, dict) and "detail" in data:
        message = str(data["detail"])
        detail = None
    elif isinstance(data, dict):
        detail = data
    else:
        message = str(data)
        detail = None
    response.data = {
        "error": {
            "code": code,
            "message": message,
            "details": detail,
        }
    }
    return response
