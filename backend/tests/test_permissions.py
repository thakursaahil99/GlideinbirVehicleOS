from types import SimpleNamespace

import pytest
from django.contrib.auth.models import AnonymousUser

from apps.accounts.constants import Role, StaffPermission
from apps.core.permissions import (
    HasStaffPermission,
    IsAgencyAdmin,
    IsAgencyManager,
    IsAgencyStaff,
    IsAgencyUser,
    IsCustomer,
    IsOwner,
    IsSameOrganization,
    IsSuperAdmin,
)
from apps.organizations.models import Membership

pytestmark = pytest.mark.django_db


def req(user):
    return SimpleNamespace(user=user)


@pytest.fixture
def people(super_admin, customer, agency_a):
    return {
        "super": super_admin, "customer": customer,
        "admin": agency_a.admin, "manager": agency_a.manager, "staff": agency_a.staff,
        "anon": AnonymousUser(),
    }


@pytest.mark.parametrize(
    "perm, allowed",
    [
        (IsSuperAdmin, {"super"}),
        (IsCustomer, {"customer"}),
        (IsAgencyUser, {"admin", "manager", "staff"}),
        (IsAgencyStaff, {"admin", "manager", "staff"}),
        (IsAgencyManager, {"admin", "manager"}),
        (IsAgencyAdmin, {"admin"}),
    ],
)
def test_role_permission_matrix(people, perm, allowed):
    for name, user in people.items():
        assert perm().has_permission(req(user), None) is (name in allowed), f"{perm.__name__} / {name}"


def test_agency_role_without_membership_is_denied(make_user):
    orphan = make_user(Role.AGENCY_ADMIN)
    assert IsAgencyAdmin().has_permission(req(orphan), None) is False


def test_staff_permission_codes(agency_a, super_admin):
    perm = HasStaffPermission(StaffPermission.BOOKING_VIEW)()
    assert perm.has_permission(req(agency_a.staff), None)          # has default code
    assert not perm.has_permission(req(agency_a.manager), None)    # fixture gives manager no codes
    assert perm.has_permission(req(agency_a.admin), None)          # admins always pass
    assert perm.has_permission(req(super_admin), None)

    refunds = HasStaffPermission(StaffPermission.PAYMENT_VIEW)()
    assert not refunds.has_permission(req(agency_a.staff), None)


def test_staff_permission_requires_all_codes(agency_a):
    Membership.objects.filter(user=agency_a.manager).update(permissions=["BOOKING_VIEW"])
    perm = HasStaffPermission("BOOKING_VIEW", "BOOKING_CANCEL")()
    assert not perm.has_permission(req(agency_a.manager), None)


def test_is_same_organization(agency_a, agency_b, super_admin):
    own = SimpleNamespace(organization_id=agency_a.org.id)
    other = SimpleNamespace(organization_id=agency_b.org.id)
    perm = IsSameOrganization()
    assert perm.has_object_permission(req(agency_a.staff), None, own)
    assert not perm.has_object_permission(req(agency_a.staff), None, other)
    assert perm.has_object_permission(req(super_admin), None, other)


def test_is_owner(make_user):
    owner, stranger = make_user(), make_user()
    obj = SimpleNamespace(user_id=owner.pk)
    assert IsOwner().has_object_permission(req(owner), None, obj)
    assert not IsOwner().has_object_permission(req(stranger), None, obj)


class TestUserManagementEndpoints:
    def test_only_super_admin_lists_users(self, auth_client, super_admin, agency_a, customer):
        assert auth_client(super_admin).get("/api/v1/users/").status_code == 200
        assert auth_client(agency_a.admin).get("/api/v1/users/").status_code == 403
        assert auth_client(customer).get("/api/v1/users/").status_code == 403

    def test_user_list_filters_by_role(self, auth_client, super_admin, agency_a, customer):
        res = auth_client(super_admin).get("/api/v1/users/?role=CUSTOMER")
        assert {u["role"] for u in res.json()["data"]} == {"CUSTOMER"}

    def test_deactivate_and_activate_user(self, api_client, auth_client, super_admin, customer):
        from .conftest import PASSWORD

        client = auth_client(super_admin)
        res = client.post(f"/api/v1/users/{customer.id}/deactivate/")
        assert res.status_code == 200 and res.json()["data"]["is_active"] is False
        assert api_client.post("/api/v1/auth/login/", {"email": customer.email, "password": PASSWORD}).status_code == 401
        assert client.post(f"/api/v1/users/{customer.id}/activate/").json()["data"]["is_active"] is True

    def test_super_admin_cannot_deactivate_self(self, auth_client, super_admin):
        res = auth_client(super_admin).post(f"/api/v1/users/{super_admin.id}/deactivate/")
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "CANNOT_MODIFY_SELF"

    def test_user_list_has_no_n_plus_one(self, auth_client, super_admin, make_agency, django_assert_max_num_queries):
        for _ in range(4):
            make_agency()
        client = auth_client(super_admin)
        with django_assert_max_num_queries(8):
            res = client.get("/api/v1/users/?page_size=50")
        assert res.status_code == 200
        assert len(res.json()["data"]) >= 12
