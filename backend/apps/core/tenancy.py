"""
Tenant resolution and tenant-aware querysets.

The tenant is ALWAYS derived from the authenticated user's active membership in
the database — never from an ``organization_id`` sent by the client and never
from JWT claims (which can be stale).
"""
from django.db import models

_MISSING = object()


def get_user_membership(user):
    """Return the user's active Membership (with organization) or None. Cached per request user object."""
    if user is None or not getattr(user, "is_authenticated", False) or not user.is_agency_user:
        return None
    cached = getattr(user, "_cached_membership", _MISSING)
    if cached is _MISSING:
        from apps.organizations.models import Membership

        cached = (
            Membership.objects.select_related("organization")
            .filter(user=user, is_active=True)
            .first()
        )
        user._cached_membership = cached
    return cached


def get_user_organization(user):
    membership = get_user_membership(user)
    return membership.organization if membership else None


def get_user_organization_id(user):
    membership = get_user_membership(user)
    return membership.organization_id if membership else None


def clear_membership_cache(user):
    if hasattr(user, "_cached_membership"):
        del user._cached_membership


class TenantQuerySet(models.QuerySet):
    """QuerySet for rows that carry an ``organization`` foreign key."""

    tenant_field = "organization"

    def for_organization(self, organization):
        org_id = getattr(organization, "pk", organization)
        return self.filter(**{f"{self.tenant_field}_id": org_id})

    def for_user(self, user):
        if user is None or not getattr(user, "is_authenticated", False):
            return self.none()
        if user.is_super_admin:
            return self
        org_id = get_user_organization_id(user)
        if org_id is None:
            return self.none()
        return self.filter(**{f"{self.tenant_field}_id": org_id})


TenantManager = models.Manager.from_queryset(TenantQuerySet)
