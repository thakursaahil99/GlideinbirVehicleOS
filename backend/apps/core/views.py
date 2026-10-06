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


class CronRemindersView(APIView):
    """
    Scheduled jobs for hosts without Celery Beat (Vercel Cron). Vercel calls it with
    ``Authorization: Bearer $CRON_SECRET``; anything else is refused.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    @extend_schema(tags=["system"], summary="Run scheduled jobs (cron only)", responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        import hmac

        from apps.accounts.tasks import cleanup_expired_tokens
        from apps.notifications.tasks import send_booking_reminder

        secret = getattr(settings, "CRON_SECRET", "")
        supplied = request.META.get("HTTP_AUTHORIZATION", "").removeprefix("Bearer ").strip()
        if not secret or not hmac.compare_digest(secret, supplied):
            return Response(error_payload("PERMISSION_DENIED", "Cron secret required."), status=403)
        sent = send_booking_reminder(hours_ahead=26)  # daily cron → cover the next day plus margin
        cleanup_expired_tokens()
        return Response({"reminders_sent": sent})


def json_404(request, exception=None):
    return JsonResponse(error_payload("NOT_FOUND", "The requested resource was not found."), status=404)


def json_500(request):
    return JsonResponse(error_payload("INTERNAL_ERROR", "An unexpected error occurred."), status=500)
