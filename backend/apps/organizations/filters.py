import django_filters

from .models import Organization, OrganizationStatus, VerificationStatus


class OrganizationFilter(django_filters.FilterSet):
    status = django_filters.MultipleChoiceFilter(choices=OrganizationStatus.choices)
    verification_status = django_filters.MultipleChoiceFilter(choices=VerificationStatus.choices)
    city = django_filters.CharFilter(lookup_expr="iexact")
    created_from = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_to = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = Organization
        fields = ("status", "verification_status", "city", "state")
