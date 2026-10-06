import pytest

from apps.accounts.constants import Role
from apps.accounts.models import User
from apps.audit_logs.models import AuditAction, AuditLog
from apps.organizations.models import Membership, Organization, OrganizationStatus, VerificationStatus

from .conftest import PASSWORD

pytestmark = pytest.mark.django_db

REGISTER_AGENCY = "/api/v1/auth/register-agency/"


def agency_payload(**overrides):
    payload = {
        "name": "Fresh Motors", "phone": "+919812345678", "email": "hello@freshmotors.in", "city": "Delhi",
        "gst_number": "27AAPFU0939F1ZV",
        "admin_full_name": "Fresh Owner", "admin_email": "owner@freshmotors.in", "admin_password": PASSWORD,
    }
    payload.update(overrides)
    return payload


class TestAgencyRegistration:
    def test_register_agency_creates_pending_org_and_admin(self, api_client):
        res = api_client.post(REGISTER_AGENCY, agency_payload())
        assert res.status_code == 201, res.json()
        data = res.json()["data"]
        org = Organization.objects.get(id=data["organization"]["id"])
        assert org.status == OrganizationStatus.PENDING
        assert org.slug == "fresh-motors"
        admin = User.objects.get(email="owner@freshmotors.in")
        assert admin.role == Role.AGENCY_ADMIN
        assert Membership.objects.filter(user=admin, organization=org, is_active=True).exists()
        assert data["user"]["organization"]["status"] == OrganizationStatus.PENDING
        assert AuditLog.objects.filter(action=AuditAction.AGENCY_REGISTERED, organization=org).exists()

    def test_client_cannot_set_status_on_registration(self, api_client):
        res = api_client.post(REGISTER_AGENCY, agency_payload(status="ACTIVE"))
        assert res.status_code == 201
        assert Organization.objects.get().status == OrganizationStatus.PENDING

    def test_invalid_gst_rejected(self, api_client):
        res = api_client.post(REGISTER_AGENCY, agency_payload(gst_number="BAD"))
        assert res.status_code == 400
        assert "gst_number" in res.json()["error"]["details"]

    def test_slug_is_unique(self, api_client):
        api_client.post(REGISTER_AGENCY, agency_payload())
        res = api_client.post(REGISTER_AGENCY, agency_payload(admin_email="two@freshmotors.in"))
        assert res.status_code == 201
        assert set(Organization.objects.values_list("slug", flat=True)) == {"fresh-motors", "fresh-motors-2"}


class TestStatusWorkflow:
    def act(self, client, org, action, reason=""):
        return client.post(f"/api/v1/organizations/{org.id}/{action}/", {"reason": reason})

    def test_super_admin_approves_pending_agency(self, auth_client, super_admin, make_agency):
        agency = make_agency(status=OrganizationStatus.PENDING)
        res = self.act(auth_client(super_admin), agency.org, "approve")
        assert res.status_code == 200
        agency.org.refresh_from_db()
        assert agency.org.status == OrganizationStatus.ACTIVE
        assert agency.org.verification_status == VerificationStatus.VERIFIED
        log = AuditLog.objects.get(action=AuditAction.AGENCY_APPROVED)
        assert log.old_data["status"] == "PENDING" and log.new_data["status"] == "ACTIVE"
        assert log.user == super_admin

    def test_suspend_requires_reason(self, auth_client, super_admin, agency_a):
        res = self.act(auth_client(super_admin), agency_a.org, "suspend")
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "REASON_REQUIRED"

    def test_suspend_then_reactivate(self, auth_client, super_admin, agency_a):
        client = auth_client(super_admin)
        assert self.act(client, agency_a.org, "suspend", "Fraud review").status_code == 200
        agency_a.org.refresh_from_db()
        assert agency_a.org.status == OrganizationStatus.SUSPENDED
        assert not agency_a.org.can_receive_bookings
        assert not Organization.objects.bookable().filter(pk=agency_a.org.pk).exists()
        assert self.act(client, agency_a.org, "reactivate").status_code == 200
        agency_a.org.refresh_from_db()
        assert agency_a.org.status == OrganizationStatus.ACTIVE

    def test_reject_pending(self, auth_client, super_admin, make_agency):
        agency = make_agency(status=OrganizationStatus.PENDING)
        assert self.act(auth_client(super_admin), agency.org, "reject", "Incomplete documents").status_code == 200
        agency.org.refresh_from_db()
        assert agency.org.status == OrganizationStatus.REJECTED
        assert agency.org.status_reason == "Incomplete documents"

    def test_invalid_transition_returns_409(self, auth_client, super_admin, agency_a):
        res = self.act(auth_client(super_admin), agency_a.org, "reject", "nope")  # ACTIVE cannot be rejected
        assert res.status_code == 409
        assert res.json()["error"]["code"] == "INVALID_STATE_TRANSITION"
        assert res.json()["error"]["details"]["current_status"] == "ACTIVE"

    @pytest.mark.parametrize("role", ["admin", "manager", "staff"])
    def test_agency_users_cannot_change_status(self, auth_client, agency_a, role):
        res = self.act(auth_client(getattr(agency_a, role)), agency_a.org, "suspend", "self")
        assert res.status_code == 403

    def test_customer_cannot_change_status(self, auth_client, customer, agency_a):
        assert self.act(auth_client(customer), agency_a.org, "approve").status_code == 403


class TestProfileUpdate:
    def test_agency_admin_updates_own_profile_and_is_audited(self, auth_client, agency_a):
        res = auth_client(agency_a.admin).patch(f"/api/v1/organizations/{agency_a.org.id}/",
                                                {"description": "Best in town", "status": "SUSPENDED"})
        assert res.status_code == 200, res.json()
        agency_a.org.refresh_from_db()
        assert agency_a.org.description == "Best in town"
        assert agency_a.org.status == OrganizationStatus.ACTIVE  # read-only through this endpoint
        log = AuditLog.objects.get(action=AuditAction.AGENCY_UPDATED)
        assert log.new_data == {"description": "Best in town"}

    @pytest.mark.parametrize("role", ["manager", "staff"])
    def test_non_admins_cannot_update_profile(self, auth_client, agency_a, role):
        res = auth_client(getattr(agency_a, role)).patch(f"/api/v1/organizations/{agency_a.org.id}/",
                                                         {"description": "x"})
        assert res.status_code == 403

    def test_put_is_not_allowed(self, auth_client, agency_a):
        res = auth_client(agency_a.admin).put(f"/api/v1/organizations/{agency_a.org.id}/", {"name": "x"})
        assert res.status_code == 405

    def test_staff_cannot_list_members(self, auth_client, agency_a):
        assert auth_client(agency_a.staff).get(f"/api/v1/organizations/{agency_a.org.id}/members/").status_code == 403

    def test_logo_upload_validates_content(self, auth_client, agency_a):
        from django.core.files.uploadedfile import SimpleUploadedFile

        fake = SimpleUploadedFile("logo.png", b"not really a png", content_type="image/png")
        res = auth_client(agency_a.admin).patch(f"/api/v1/organizations/{agency_a.org.id}/", {"logo": fake},
                                                format="multipart")
        assert res.status_code == 400
        assert "logo" in res.json()["error"]["details"]

    def test_valid_logo_upload(self, auth_client, agency_a):
        import io

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (64, 64), "red").save(buf, format="PNG")
        logo = SimpleUploadedFile("my logo.png", buf.getvalue(), content_type="image/png")
        res = auth_client(agency_a.admin).patch(f"/api/v1/organizations/{agency_a.org.id}/", {"logo": logo},
                                                format="multipart")
        assert res.status_code == 200, res.json()
        agency_a.org.refresh_from_db()
        assert agency_a.org.logo.name.startswith("organizations/logos/")
        assert "my logo" not in agency_a.org.logo.name  # client filename never reaches storage
