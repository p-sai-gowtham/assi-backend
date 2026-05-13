from __future__ import annotations

from rest_framework.views import exception_handler as drf_exception_handler


def exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is not None and isinstance(response.data, dict):
        request = context.get("request")
        detail = response.data.get("detail") or response.data.get("non_field_errors") or response.data
        response.data.setdefault("status_code", response.status_code)
        response.data.setdefault(
            "error",
            {
                "code": getattr(exc, "default_code", "error"),
                "message": detail[0] if isinstance(detail, list) and detail else detail,
                "details": response.data.copy(),
                "request_id": getattr(request, "request_id", ""),
            },
        )
    return response
