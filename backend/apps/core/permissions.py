"""
DRF permission classes.

Role hierarchy inside an agency: AGENCY_ADMIN > AGENCY_MANAGER > AGENCY_STAFF.
``IsAgencyManager`` admits admins and managers; ``IsAgencyStaff`` admits every
agency role (it is equivalent to ``IsAgencyUser``). Agency permissions also
require an *active* membership, which is what scopes data to one tenant.
"""
from rest_framework.permissions import BasePermission

from apps.accounts.constants import Role
from apps.core.tenancy import get_user_membership, get_user_organization_id


def _authenticated(request):
    return bool(request.user and request.user.is_authenticated)


class IsSuperAdmin(BasePermission):
    message = "Super Admin access required."

    def has_permission(self, request, view):
        return _authenticated(request) and request.user.role == Role.SUPER_ADMIN


class IsCustomer(BasePermission):
    message = "Customer access required."

    def has_permission(self, request, view):
        return _authenticated(request) and request.user.role == Role.CUSTOMER


class _AgencyRolePermission(BasePermission):
    allowed_roles: frozenset = frozenset()
    message = "Agency access required."

    def has_permission(self, request, view):
        if not _authenticated(request) or request.user.role not in self.allowed_roles:
            return False
        return get_user_membership(request.user) is not None


class IsAgencyUser(_AgencyRolePermission):
    allowed_roles = frozenset({Role.AGENCY_ADMIN, Role.AGENCY_MANAGER, Role.AGENCY_STAFF})


class IsAgencyStaff(IsAgencyUser):
    """Any agency member (admin, manager or staff)."""


class IsAgencyManager(_AgencyRolePermission):
    allowed_roles = frozenset({Role.AGENCY_ADMIN, Role.AGENCY_MANAGER})
    message = "Agency manager access required."


class IsAgencyAdmin(_AgencyRolePermission):
    allowed_roles = frozenset({Role.AGENCY_ADMIN})
    message = "Agency admin access required."


class IsSameOrganization(BasePermission):
    """Object-level: the object's organization must be the user's organization (Super Admin bypasses)."""

    message = "You do not have access to this organization's data."
    organization_attr = "organization_id"

    def has_permission(self, request, view):
        return _authenticated(request)

    def has_object_permission(self, request, view, obj):
        if request.user.role == Role.SUPER_ADMIN:
            return True
        user_org_id = get_user_organization_id(request.user)
        if user_org_id is None:
            return False
        # Views may override the attribute, e.g. "pk" when the object *is* the organization.
        attr = getattr(view, "object_organization_attr", self.organization_attr)
        return getattr(obj, attr, None) == user_org_id


class IsOwner(BasePermission):
    """Object-level: the object belongs to the requesting user (``obj.user`` or ``obj.owner``)."""

    message = "You do not own this resource."

    def has_permission(self, request, view):
        return _authenticated(request)

    def has_object_permission(self, request, view, obj):
        if request.user.role == Role.SUPER_ADMIN:
            return True
        owner_id = getattr(obj, "user_id", None) or getattr(obj, "owner_id", None)
        if owner_id is None and obj.__class__ is request.user.__class__:
            owner_id = obj.pk
        return owner_id == request.user.pk


def HasStaffPermission(*codes):  # noqa: N802 - reads like a class at call sites
    """
    Factory for a permission class requiring granular staff permission codes.

    Super Admin and Agency Admin always pass; managers and staff must hold every
    listed code on their active membership.
    """

    class _HasStaffPermission(BasePermission):
        message = "You do not have permission to perform this action."
        required_codes = frozenset(codes)

        def has_permission(self, request, view):
            if not _authenticated(request):
                return False
            if request.user.role == Role.SUPER_ADMIN:
                return True
            membership = get_user_membership(request.user)
            if membership is None:
                return False
            return all(membership.has_permission(code) for code in self.required_codes)

    _HasStaffPermission.__name__ = f"HasStaffPermission_{'_'.join(codes)}"
    return _HasStaffPermission
