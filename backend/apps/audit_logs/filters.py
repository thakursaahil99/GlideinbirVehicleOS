import django_filters

from .models import AuditAction, AuditLog


class AuditLogFilter(django_filters.FilterSet):
    action = django_filters.MultipleChoiceFilter(choices=AuditAction.choices)
    created_from = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_to = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = AuditLog
        fields = ("action", "user", "organization", "model_name", "object_id")
