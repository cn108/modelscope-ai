"""Consistent API error shape (specification section 8)."""

from rest_framework.views import exception_handler


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
    else:
        detail = data
    response.data = {
        "error": {
            "code": code,
            "message": message,
            "details": detail,
        }
    }
    return response
