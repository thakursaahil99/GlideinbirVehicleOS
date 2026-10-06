import logging

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .exceptions import error_payload

logger = logging.getLogger(__name__)


class HealthView(APIView):
    """Liveness/readiness probe for Docker and load balancers."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    @extend_schema(tags=["system"], summary="Health check", responses={200: OpenApiTypes.OBJECT,
                                                                       503: OpenApiTypes.OBJECT})
    def get(self, request):
        checks = {"database": "ok", "cache": "ok"}
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except Exception:  # noqa: BLE001
            logger.exception("Health check: database unavailable")
            checks["database"] = "error"
        try:
            cache.set("healthcheck", "1", 5)
            if cache.get("healthcheck") != "1":
                checks["cache"] = "error"
        except Exception:  # noqa: BLE001
            logger.exception("Health check: cache unavailable")
            checks["cache"] = "error"

        healthy = all(v == "ok" for v in checks.values())
        return Response(
            {"status": "ok" if healthy else "degraded", **checks, "service": settings.PROJECT_NAME,
             "built_by": settings.PROJECT_AUTHOR},
            status=200 if healthy else 503,
        )


def json_404(request, exception=None):
    return JsonResponse(error_payload("NOT_FOUND", "The requested resource was not found."), status=404)


def json_500(request):
    return JsonResponse(error_payload("INTERNAL_ERROR", "An unexpected error occurred."), status=500)
