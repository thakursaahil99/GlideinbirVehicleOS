"""
Mandatory tenant-isolation tests: an agency must never read or write another
agency's data. Cross-tenant access must return 403 or 404.
"""
import pytest

from apps.audit_logs.models import AuditAction
from apps.audit_logs.services import AuditService
from apps.core.tenancy import get_user_organization_id
from apps.organizations.models import Membership, Organization

pytestmark = pytest.mark.django_db

ORGS = "/api/v1/organizations/"


def org_url(org, suffix=""):
    return f"{ORGS}{org.id}/{suffix}"


class TestOrganizationIsolation:
    def test_agency_lists_only_its_own_organization(self, auth_client, agency_a, agency_b):
        res = auth_client(agency_a.admin).get(ORGS)
        assert res.status_code == 200
        ids = [o["id"] for o in res.json()["data"]]
        assert ids == [str(agency_a.org.id)]

    @pytest.mark.parametrize("role", ["admin", "manager", "staff"])
    def test_agency_cannot_retrieve_other_agency(self, auth_client, agency_a, agency_b, role):
        res = auth_client(getattr(agency_a, role)).get(org_url(agency_b.org))
        assert res.status_code in (403, 404)
        assert res.json()["success"] is False

    def test_agency_admin_cannot_update_other_agency(self, auth_client, agency_a, agency_b):
        res = auth_client(agency_a.admin).patch(org_url(agency_b.org), {"name": "Hijacked"})
        assert res.status_code in (403, 404)
        agency_b.org.refresh_from_db()
        assert agency_b.org.name == "Agency B"

    def test_agency_cannot_list_other_agency_members(self, auth_client, agency_a, agency_b):
        res = auth_client(agency_a.admin).get(org_url(agency_b.org, "members/"))
        assert res.status_code in (403, 404)

    def test_members_endpoint_only_returns_own_members(self, auth_client, agency_a, agency_b):
        res = auth_client(agency_a.admin).get(org_url(agency_a.org, "members/"))
        assert res.status_code == 200
        emails = {m["user"]["email"] for m in res.json()["data"]}
        assert emails == {agency_a.admin.email, agency_a.manager.email, agency_a.staff.email}

    def test_super_admin_sees_every_agency(self, auth_client, super_admin, agency_a, agency_b):
        res = auth_client(super_admin).get(ORGS)
        assert {o["id"] for o in res.json()["data"]} == {str(agency_a.org.id), str(agency_b.org.id)}
        assert auth_client(super_admin).get(org_url(agency_b.org)).status_code == 200

    def test_customer_has_no_access_to_agency_data(self, auth_client, customer, agency_a):
        assert auth_client(customer).get(ORGS).status_code == 403
        assert auth_client(customer).get(org_url(agency_a.org)).status_code in (403, 404)

    def test_deactivated_membership_loses_tenant_access(self, auth_client, agency_a):
        Membership.objects.filter(user=agency_a.staff).update(is_active=False)
        assert auth_client(agency_a.staff).get(org_url(agency_a.org)).status_code in (403, 404)


class TestTenantQuerysets:
    def test_tenant_comes_from_membership_not_request(self, agency_a, agency_b):
        assert get_user_organization_id(agency_a.admin) == agency_a.org.id

    def test_membership_queryset_is_scoped(self, agency_a, agency_b):
        visible = Membership.objects.for_user(agency_a.manager)
        assert set(visible.values_list("organization_id", flat=True)) == {agency_a.org.id}

    def test_anonymous_and_customer_get_nothing(self, customer, agency_a):
        from django.contrib.auth.models import AnonymousUser

        assert not Organization.objects.for_user(AnonymousUser()).exists()
        assert not Organization.objects.for_user(customer).exists()
        assert not Membership.objects.for_user(customer).exists()

    def test_one_active_membership_per_user_is_db_enforced(self, agency_a, agency_b):
        from django.db import IntegrityError, transaction

        with pytest.raises(IntegrityError), transaction.atomic():
            Membership.objects.create(user=agency_a.staff, organization=agency_b.org, is_active=True)


class TestAuditLogIsolation:
    def test_agency_admin_sees_only_own_audit_logs(self, auth_client, agency_a, agency_b):
        AuditService.log(AuditAction.AGENCY_UPDATED, user=agency_a.admin, organization=agency_a.org,
                         instance=agency_a.org)
        AuditService.log(AuditAction.AGENCY_UPDATED, user=agency_b.admin, organization=agency_b.org,
                         instance=agency_b.org)
        res = auth_client(agency_a.admin).get("/api/v1/audit-logs/")
        assert res.status_code == 200
        orgs = {row["organization"] for row in res.json()["data"]}
        assert orgs == {str(agency_a.org.id)}

    def test_agency_admin_cannot_filter_into_other_tenant(self, auth_client, agency_a, agency_b):
        AuditService.log(AuditAction.AGENCY_UPDATED, organization=agency_b.org, instance=agency_b.org)
        res = auth_client(agency_a.admin).get(f"/api/v1/audit-logs/?organization={agency_b.org.id}")
        assert res.status_code == 200
        assert res.json()["data"] == []

    def test_staff_cannot_read_audit_logs(self, auth_client, agency_a):
        assert auth_client(agency_a.staff).get("/api/v1/audit-logs/").status_code == 403
