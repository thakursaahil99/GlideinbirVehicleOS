from rest_framework.exceptions import PermissionDenied

from apps.core.tenancy import get_user_organization


class TenantScopedViewSetMixin:
    """
    Scopes ``get_queryset`` to the requesting user's tenant and stamps new rows
    with the user's organization. Any ``organization`` value in the payload is
    ignored, so a client can never write into another tenant.

    Super Admins read across tenants and may narrow with ``?organization=<id>``.
    Writes always require an agency membership (Super Admins manage tenant
    records through the Django admin).
    """

    def get_queryset(self):
        qs = super().get_queryset().for_user(self.request.user)
        org_filter = self.request.query_params.get("organization")
        if org_filter and self.request.user.is_super_admin:
            qs = qs.filter(organization_id=org_filter)
        return qs

    def get_tenant(self):
        organization = get_user_organization(self.request.user)
        if organization is None:
            raise PermissionDenied("An active agency membership is required for this action.")
        return organization

    def perform_create(self, serializer):
        serializer.save(organization=self.get_tenant())
