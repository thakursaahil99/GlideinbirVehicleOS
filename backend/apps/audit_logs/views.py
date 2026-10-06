from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import viewsets

from apps.core.permissions import IsAgencyAdmin, IsSuperAdmin

from .filters import AuditLogFilter
from .models import AuditLog
from .serializers import AuditLogSerializer


@extend_schema_view(
    list=extend_schema(tags=["audit-logs"], summary="List audit logs (Super Admin: all, Agency Admin: own agency)"),
    retrieve=extend_schema(tags=["audit-logs"], summary="Retrieve an audit log entry"),
)
class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AuditLogSerializer
    permission_classes = [IsSuperAdmin | IsAgencyAdmin]
    filterset_class = AuditLogFilter
    search_fields = ("model_name", "object_id", "user__email")
    ordering_fields = ("created_at", "action")

    def get_queryset(self):
        return AuditLog.objects.for_user(self.request.user).select_related("user", "organization")
