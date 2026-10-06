"""Super Admin creates users and agencies; agency admins add their own staff with a password."""
import pytest
from django.core import mail

from apps.accounts.constants import Role
from apps.accounts.models import User
from apps.audit_logs.models import AuditAction, AuditLog
from apps.customers.models import Customer
from apps.organizations.models import Membership, Organization, OrganizationStatus, VerificationStatus

from .conftest import PASSWORD

pytestmark = pytest.mark.django_db

USERS = "/api/v1/users/"
ORGS = "/api/v1/organizations/"
STAFF = "/api/v1/agency/staff/"


def login_ok(api_client, email, password=PASSWORD):
    return api_client.post("/api/v1/auth/login/", {"email": email, "password": password}).status_code == 200


class TestAdminCreateUser:
    def test_create_customer_with_password(self, auth_client, super_admin, api_client):
        res = auth_client(super_admin).post(USERS, {"email": "New@Example.com", "full_name": "New Customer",
                                                    "role": "CUSTOMER", "password": PASSWORD})
        assert res.status_code == 201, res.content
        user = User.objects.get(email="new@example.com")
        assert user.role == Role.CUSTOMER and user.email_verified
        assert Customer.objects.filter(user=user).exists()
        assert login_ok(api_client, "new@example.com")
        assert AuditLog.objects.filter(action=AuditAction.USER_CREATED, user=super_admin).exists()

    def test_create_super_admin(self, auth_client, super_admin):
        res = auth_client(super_admin).post(USERS, {"email": "boss@example.com", "full_name": "Boss",
                                                    "role": "SUPER_ADMIN", "password": PASSWORD})
        assert res.status_code == 201
        user = User.objects.get(email="boss@example.com")
        assert user.is_super_admin and user.is_staff

    def test_agency_role_requires_organization(self, auth_client, super_admin):
        res = auth_client(super_admin).post(USERS, {"email": "s@example.com", "full_name": "S",
                                                    "role": "AGENCY_STAFF", "password": PASSWORD})
        assert res.status_code == 400
        assert not User.objects.filter(email="s@example.com").exists()

    def test_agency_staff_joins_agency(self, auth_client, super_admin, agency_a, api_client):
        res = auth_client(super_admin).post(USERS, {"email": "tech@example.com", "full_name": "Tech",
                                                    "role": "AGENCY_STAFF", "organization": str(agency_a.org.pk),
                                                    "password": PASSWORD})
        assert res.status_code == 201, res.content
        assert res.json()["data"]["organization"]["id"] == str(agency_a.org.pk)
        assert Membership.objects.filter(user__email="tech@example.com", organization=agency_a.org).exists()
        assert login_ok(api_client, "tech@example.com")

    def test_without_password_sends_link(self, auth_client, super_admin, django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks(execute=True):
            res = auth_client(super_admin).post(USERS, {"email": "invite@example.com", "full_name": "Invitee",
                                                        "role": "CUSTOMER"})
        assert res.status_code == 201
        assert not User.objects.get(email="invite@example.com").has_usable_password()
        assert any("invite@example.com" in m.to for m in mail.outbox)

    def test_duplicate_email_and_weak_password_rejected(self, auth_client, super_admin, customer):
        client = auth_client(super_admin)
        assert client.post(USERS, {"email": customer.email, "full_name": "X", "role": "CUSTOMER",
                                   "password": PASSWORD}).status_code == 400
        assert client.post(USERS, {"email": "weak@example.com", "full_name": "X", "role": "CUSTOMER",
                                   "password": "123"}).status_code == 400

    @pytest.mark.parametrize("role", ["admin", "manager", "staff"])
    def test_agency_users_cannot_use_platform_create(self, auth_client, agency_a, role):
        res = auth_client(getattr(agency_a, role)).post(USERS, {"email": "x@example.com", "full_name": "X",
                                                                "role": "SUPER_ADMIN", "password": PASSWORD})
        assert res.status_code == 403
        assert not User.objects.filter(email="x@example.com").exists()


class TestAdminCreateAgency:
    payload = {
        "name": "Fresh Motors", "phone": "+919811111111", "email": "fresh@example.com", "city": "Delhi",
        "admin_full_name": "Fresh Admin", "admin_email": "owner@fresh.example.com",
    }

    def test_creates_active_agency_with_admin(self, auth_client, super_admin, api_client):
        res = auth_client(super_admin).post(ORGS, {**self.payload, "admin_password": PASSWORD})
        assert res.status_code == 201, res.content
        org = Organization.objects.get(name="Fresh Motors")
        assert org.status == OrganizationStatus.ACTIVE and org.verification_status == VerificationStatus.VERIFIED
        admin = User.objects.get(email="owner@fresh.example.com")
        assert admin.role == Role.AGENCY_ADMIN
        assert Membership.objects.filter(user=admin, organization=org, is_active=True).exists()
        assert login_ok(api_client, admin.email)
        assert AuditLog.objects.filter(action=AuditAction.AGENCY_REGISTERED, user=super_admin).exists()

    def test_invite_when_no_password(self, auth_client, super_admin, django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks(execute=True):
            assert auth_client(super_admin).post(ORGS, self.payload).status_code == 201
        assert not User.objects.get(email="owner@fresh.example.com").has_usable_password()
        assert any("owner@fresh.example.com" in m.to for m in mail.outbox)

    @pytest.mark.parametrize("role", ["admin", "manager", "staff"])
    def test_agency_users_cannot_create_agencies(self, auth_client, agency_a, role):
        assert auth_client(getattr(agency_a, role)).post(ORGS, self.payload).status_code == 403
        assert not Organization.objects.filter(name="Fresh Motors").exists()

    def test_customer_cannot_create_agency(self, auth_client, customer):
        assert auth_client(customer).post(ORGS, self.payload).status_code == 403


class TestAgencyAdminAddsStaffWithPassword:
    def test_staff_can_log_in_immediately(self, auth_client, agency_a, api_client, django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks(execute=True):
            res = auth_client(agency_a.admin).post(STAFF, {"email": "mech@example.com", "full_name": "Mechanic",
                                                           "role": "AGENCY_STAFF", "password": PASSWORD})
        assert res.status_code == 201, res.content
        assert login_ok(api_client, "mech@example.com")
        assert not mail.outbox

    def test_weak_password_rejected(self, auth_client, agency_a):
        res = auth_client(agency_a.admin).post(STAFF, {"email": "mech@example.com", "full_name": "Mechanic",
                                                       "role": "AGENCY_STAFF", "password": "abc"})
        assert res.status_code == 400


class TestAdminEditUser:
    def test_edit_details_and_reset_password(self, auth_client, super_admin, customer, api_client):
        res = auth_client(super_admin).patch(f"{USERS}{customer.pk}/", {"full_name": "Renamed", "phone": "+919800011122",
                                                                       "password": "N3w!Passw0rd"})
        assert res.status_code == 200, res.content
        customer.refresh_from_db()
        assert customer.full_name == "Renamed"
        assert Customer.objects.get(user=customer).full_name == "Renamed"
        assert login_ok(api_client, customer.email, "N3w!Passw0rd")
        assert AuditLog.objects.filter(action=AuditAction.USER_UPDATED, user=super_admin).exists()

    def test_duplicate_email_rejected(self, auth_client, super_admin, customer, make_user):
        other = make_user()
        assert auth_client(super_admin).patch(f"{USERS}{customer.pk}/", {"email": other.email}).status_code == 400

    def test_agency_admin_cannot_edit_users(self, auth_client, agency_a, customer):
        assert auth_client(agency_a.admin).patch(f"{USERS}{customer.pk}/", {"full_name": "X"}).status_code == 403
