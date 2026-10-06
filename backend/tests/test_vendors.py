import pytest
from django.core import mail

from apps.accounts.constants import Role
from apps.accounts.models import User
from apps.audit_logs.models import AuditAction, AuditLog
from apps.organizations.models import Membership, OrganizationStatus
from apps.vendors.models import Holiday, ResourceType, ServiceResource, WorkingHours

from .conftest import PASSWORD

pytestmark = pytest.mark.django_db

STAFF = "/api/v1/agency/staff/"


class TestStaffManagement:
    def test_admin_adds_staff_and_invite_is_sent(self, auth_client, agency_a, django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks(execute=True):
            res = auth_client(agency_a.admin).post(STAFF, {"email": "New.Tech@Example.com", "full_name": "New Tech",
                                                           "role": Role.AGENCY_STAFF})
        assert res.status_code == 201, res.json()
        data = res.json()["data"]
        assert data["email"] == "new.tech@example.com"
        assert "BOOKING_VIEW" in data["permissions"]  # default staff permissions
        user = User.objects.get(email="new.tech@example.com")
        assert not user.has_usable_password()
        assert Membership.objects.get(user=user).organization == agency_a.org
        assert len(mail.outbox) == 1 and agency_a.org.name in mail.outbox[0].subject
        assert "reset-password?uid=" in mail.outbox[0].body

    def test_custom_permissions_validated(self, auth_client, agency_a):
        res = auth_client(agency_a.admin).post(STAFF, {"email": "x@e.com", "full_name": "X", "role": "AGENCY_STAFF",
                                                       "permissions": ["NOT_A_CODE"]})
        assert res.status_code == 400

    def test_cannot_attach_existing_account(self, auth_client, agency_a, customer):
        res = auth_client(agency_a.admin).post(STAFF, {"email": customer.email, "full_name": "X",
                                                       "role": "AGENCY_STAFF"})
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "EMAIL_TAKEN"

    def test_agency_admin_cannot_create_admin(self, auth_client, agency_a):
        res = auth_client(agency_a.admin).post(STAFF, {"email": "boss@e.com", "full_name": "B",
                                                       "role": "AGENCY_ADMIN"})
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "CANNOT_MANAGE_ADMIN"

    @pytest.mark.parametrize("role", ["manager", "staff"])
    def test_non_admins_cannot_add_staff(self, auth_client, agency_a, role):
        res = auth_client(getattr(agency_a, role)).post(STAFF, {"email": "x@e.com", "full_name": "X",
                                                                "role": "AGENCY_STAFF"})
        assert res.status_code == 403

    def test_manager_can_list_staff_but_staff_cannot(self, auth_client, agency_a):
        assert auth_client(agency_a.manager).get(STAFF).status_code == 200
        assert auth_client(agency_a.staff).get(STAFF).status_code == 403

    def test_update_permissions_and_role_is_audited(self, auth_client, agency_a):
        m = Membership.objects.get(user=agency_a.staff)
        res = auth_client(agency_a.admin).patch(f"{STAFF}{m.id}/", {"permissions": ["BOOKING_VIEW", "REPORT_VIEW"],
                                                                    "role": "AGENCY_MANAGER"})
        assert res.status_code == 200, res.json()
        assert res.json()["data"]["role"] == "AGENCY_MANAGER"
        assert res.json()["data"]["permissions"] == ["BOOKING_VIEW", "REPORT_VIEW"]
        assert AuditLog.objects.filter(action=AuditAction.PERMISSIONS_CHANGED, organization=agency_a.org).exists()
        assert AuditLog.objects.filter(action=AuditAction.ROLE_CHANGED).exists()

    def test_admin_cannot_modify_self_or_other_admins(self, auth_client, agency_a):
        own = Membership.objects.get(user=agency_a.admin)
        res = auth_client(agency_a.admin).post(f"{STAFF}{own.id}/deactivate/")
        assert res.status_code == 400 and res.json()["error"]["code"] == "CANNOT_MODIFY_SELF"

    def test_deactivate_blocks_login_and_reactivate_restores(self, api_client, auth_client, agency_a):
        m = Membership.objects.get(user=agency_a.staff)
        client = auth_client(agency_a.admin)
        assert client.post(f"{STAFF}{m.id}/deactivate/").status_code == 200
        login = api_client.post("/api/v1/auth/login/", {"email": agency_a.staff.email, "password": PASSWORD})
        assert login.status_code == 401
        assert client.post(f"{STAFF}{m.id}/activate/").status_code == 200
        login = api_client.post("/api/v1/auth/login/", {"email": agency_a.staff.email, "password": PASSWORD})
        assert login.status_code == 200

    def test_cross_tenant_staff_is_invisible(self, auth_client, agency_a, agency_b):
        other = Membership.objects.get(user=agency_b.staff)
        client = auth_client(agency_a.admin)
        assert client.get(f"{STAFF}{other.id}/").status_code == 404
        assert client.patch(f"{STAFF}{other.id}/", {"permissions": []}).status_code == 404
        assert client.post(f"{STAFF}{other.id}/deactivate/").status_code == 404
        emails = {row["email"] for row in client.get(STAFF).json()["data"]}
        assert agency_b.staff.email not in emails

    def test_permission_codes_endpoint(self, auth_client, agency_a):
        res = auth_client(agency_a.manager).get(f"{STAFF}permission-codes/")
        assert res.status_code == 200
        assert {"code": "BOOKING_VIEW", "label": "View bookings"} in res.json()["data"]


class TestSchedule:
    URL = "/api/v1/agency/working-hours/"

    def test_replace_week_with_split_shifts(self, auth_client, agency_a):
        week = [{"weekday": d, "opens_at": "09:00", "closes_at": "13:00"} for d in range(6)]
        week += [{"weekday": d, "opens_at": "14:00", "closes_at": "19:00"} for d in range(6)]
        res = auth_client(agency_a.admin).put(f"{self.URL}week/", {"intervals": week})
        assert res.status_code == 200, res.json()
        assert len(res.json()["data"]) == 12
        assert WorkingHours.objects.filter(organization=agency_a.org, weekday=6).count() == 0  # Sunday closed
        assert AuditLog.objects.filter(action=AuditAction.SCHEDULE_CHANGED).exists()

        # Replacing is atomic and complete.
        res = auth_client(agency_a.admin).put(f"{self.URL}week/", {"intervals": week[:1]})
        assert WorkingHours.objects.filter(organization=agency_a.org).count() == 1

    def test_overlapping_intervals_rejected(self, auth_client, agency_a):
        res = auth_client(agency_a.admin).put(f"{self.URL}week/", {"intervals": [
            {"weekday": 0, "opens_at": "09:00", "closes_at": "13:00"},
            {"weekday": 0, "opens_at": "12:00", "closes_at": "15:00"}]})
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "OVERLAPPING_INTERVALS"

    def test_close_before_open_rejected(self, auth_client, agency_a):
        res = auth_client(agency_a.admin).put(f"{self.URL}week/", {"intervals": [
            {"weekday": 0, "opens_at": "18:00", "closes_at": "09:00"}]})
        assert res.status_code == 400

    def test_staff_reads_but_cannot_change_schedule(self, auth_client, agency_a):
        assert auth_client(agency_a.staff).get(self.URL).status_code == 200
        assert auth_client(agency_a.staff).put(f"{self.URL}week/", {"intervals": []}).status_code == 403

    def test_schedule_is_tenant_scoped(self, auth_client, agency_a, agency_b):
        WorkingHours.objects.create(organization=agency_b.org, weekday=0, opens_at="08:00", closes_at="10:00")
        assert auth_client(agency_a.admin).get(self.URL).json()["data"] == []

    def test_super_admin_reads_with_org_filter(self, auth_client, super_admin, agency_a, agency_b):
        WorkingHours.objects.create(organization=agency_b.org, weekday=0, opens_at="08:00", closes_at="10:00")
        WorkingHours.objects.create(organization=agency_a.org, weekday=1, opens_at="08:00", closes_at="10:00")
        res = auth_client(super_admin).get(f"{self.URL}?organization={agency_b.org.id}")
        assert [r["weekday"] for r in res.json()["data"]] == [0]
        assert auth_client(super_admin).put(f"{self.URL}week/", {"intervals": []}).status_code == 403

    def test_special_day(self, auth_client, agency_a):
        url = "/api/v1/agency/special-days/set-day/"
        res = auth_client(agency_a.admin).put(url, {"date": "2026-12-27", "intervals": [
            {"opens_at": "10:00", "closes_at": "14:00", "note": "Sunday camp"}]})
        assert res.status_code == 200, res.json()
        assert len(res.json()["data"]) == 1
        res = auth_client(agency_a.admin).put(url, {"date": "2026-12-27", "intervals": []})
        assert res.json()["data"] == []


class TestHolidays:
    URL = "/api/v1/agency/holidays/"

    def test_crud_and_validation(self, auth_client, agency_a):
        client = auth_client(agency_a.admin)
        res = client.post(self.URL, {"name": "Diwali", "start_date": "2026-11-08", "end_date": "2026-11-09"})
        assert res.status_code == 201, res.json()
        hid = res.json()["data"]["id"]
        assert client.patch(f"{self.URL}{hid}/", {"end_date": "2026-11-01"}).status_code == 400
        assert client.patch(f"{self.URL}{hid}/", {"kind": "EMERGENCY_CLOSURE"}).status_code == 200
        assert client.delete(f"{self.URL}{hid}/").status_code == 204
        assert not Holiday.objects.exists()

    def test_organization_in_payload_is_ignored(self, auth_client, agency_a, agency_b):
        res = auth_client(agency_a.admin).post(self.URL, {"name": "X", "start_date": "2026-11-08",
                                                          "end_date": "2026-11-08",
                                                          "organization": str(agency_b.org.id)})
        assert res.status_code == 201
        assert Holiday.objects.get().organization == agency_a.org

    def test_cross_tenant_holiday_404(self, auth_client, agency_a, agency_b):
        h = Holiday.objects.create(organization=agency_b.org, name="B", start_date="2026-11-08",
                                   end_date="2026-11-08")
        client = auth_client(agency_a.admin)
        assert client.get(f"{self.URL}{h.id}/").status_code == 404
        assert client.delete(f"{self.URL}{h.id}/").status_code == 404
        assert Holiday.objects.filter(pk=h.pk).exists()


class TestResources:
    URL = "/api/v1/agency/resources/"

    def test_create_bay_and_technician(self, auth_client, agency_a):
        client = auth_client(agency_a.admin)
        assert client.post(self.URL, {"name": "Bay 1", "resource_type": "BAY"}).status_code == 201
        res = client.post(self.URL, {"name": "Technician A", "resource_type": "TECHNICIAN",
                                     "staff": str(agency_a.staff.id)})
        assert res.status_code == 201, res.json()
        assert res.json()["data"]["staff_name"] == agency_a.staff.full_name

    def test_duplicate_name_rejected(self, auth_client, agency_a):
        client = auth_client(agency_a.admin)
        client.post(self.URL, {"name": "Bay 1", "resource_type": "BAY"})
        assert client.post(self.URL, {"name": "bay 1", "resource_type": "BAY"}).status_code == 400

    def test_cannot_link_other_agency_staff(self, auth_client, agency_a, agency_b):
        res = auth_client(agency_a.admin).post(self.URL, {"name": "Tech", "resource_type": "TECHNICIAN",
                                                          "staff": str(agency_b.staff.id)})
        assert res.status_code == 400
        assert "staff" in res.json()["error"]["details"]

    def test_staff_link_requires_technician_type(self, auth_client, agency_a):
        res = auth_client(agency_a.admin).post(self.URL, {"name": "Bay", "resource_type": "BAY",
                                                          "staff": str(agency_a.staff.id)})
        assert res.status_code == 400

    def test_resources_tenant_scoped(self, auth_client, agency_a, agency_b):
        r = ServiceResource.objects.create(organization=agency_b.org, name="B bay", resource_type=ResourceType.BAY)
        client = auth_client(agency_a.admin)
        assert client.get(f"{self.URL}{r.id}/").status_code == 404
        assert client.patch(f"{self.URL}{r.id}/", {"active": False}).status_code == 404


class TestAgencySettings:
    URL = "/api/v1/agency/settings/"

    def test_defaults_and_update(self, auth_client, agency_a):
        res = auth_client(agency_a.staff).get(self.URL)
        assert res.status_code == 200
        assert res.json()["data"]["max_advance_days"] == 30
        res = auth_client(agency_a.admin).patch(self.URL, {"buffer_minutes": 15, "auto_confirm_bookings": True})
        assert res.status_code == 200
        assert res.json()["data"]["buffer_minutes"] == 15
        log = AuditLog.objects.get(action=AuditAction.SETTINGS_CHANGED)
        assert log.new_data == {"buffer_minutes": 15, "auto_confirm_bookings": True}

    def test_validation_and_permissions(self, auth_client, agency_a, customer):
        assert auth_client(agency_a.admin).patch(self.URL, {"max_advance_days": 0}).status_code == 400
        assert auth_client(agency_a.manager).patch(self.URL, {"buffer_minutes": 5}).status_code == 403
        assert auth_client(customer).get(self.URL).status_code == 403


class TestVendorDirectory:
    URL = "/api/v1/vendors/"

    def test_only_active_agencies_with_public_fields(self, auth_client, customer, make_agency):
        active = make_agency("Open Garage")
        make_agency("Waiting Garage", status=OrganizationStatus.PENDING)
        make_agency("Bad Garage", status=OrganizationStatus.SUSPENDED)
        res = auth_client(customer).get(self.URL)
        assert res.status_code == 200
        rows = res.json()["data"]
        assert [r["name"] for r in rows] == ["Open Garage"]
        assert "status_reason" not in rows[0] and "gst_number" not in rows[0] and "member_count" not in rows[0]
        assert auth_client(customer).get(f"{self.URL}{active.org.id}/").status_code == 200

    def test_suspended_agency_profile_hidden(self, auth_client, customer, make_agency):
        hidden = make_agency(status=OrganizationStatus.SUSPENDED)
        assert auth_client(customer).get(f"{self.URL}{hidden.org.id}/").status_code == 404

    def test_hours_endpoint(self, auth_client, customer, agency_a):
        WorkingHours.objects.create(organization=agency_a.org, weekday=0, opens_at="09:00", closes_at="13:00")
        res = auth_client(customer).get(f"{self.URL}{agency_a.org.id}/hours/")
        assert res.status_code == 200
        assert res.json()["data"]["weekly"][0]["weekday_display"] == "Monday"

    def test_requires_authentication(self, api_client):
        assert api_client.get(self.URL).status_code == 401
