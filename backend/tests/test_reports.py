from decimal import Decimal

import pytest
from django.utils import timezone

from apps.bookings.models import Booking
from apps.bookings.services import BookingService
from apps.invoices.services import InvoiceService
from apps.organizations.models import Membership
from apps.payments.services import PaymentService

from .conftest import at, next_weekday

pytestmark = pytest.mark.django_db


@pytest.fixture
def paid_booking(shop, booker, make_offering, agency_b):
    """A completed, invoiced and fully paid booking at agency A, plus noise at agency B."""
    c = booker()
    booking = BookingService.create(actor=c.user, vehicle_id=c.vehicle.id, vendor_service_id=shop.offering.id,
                                    start_datetime=at(next_weekday(0), "09:00"))
    Booking.objects.filter(pk=booking.pk).update(status="COMPLETED", booking_date=timezone.localdate())
    invoice = InvoiceService.generate_for_booking(booking)
    PaymentService.pay_online(actor=c.user, method="UPI", invoice_id=invoice.id)
    # Agency B activity that must never leak into agency A's numbers.
    other = make_offering(agency_b, "oil-change")
    from apps.vendors.models import WorkingHours

    WorkingHours.objects.create(organization=agency_b.org, weekday=0, opens_at="09:00", closes_at="18:00")
    c2 = booker()
    b2 = BookingService.create(actor=c2.user, vehicle_id=c2.vehicle.id, vendor_service_id=other.id,
                               start_datetime=at(next_weekday(0), "09:00"))
    Booking.objects.filter(pk=b2.pk).update(status="COMPLETED", booking_date=timezone.localdate())
    inv2 = InvoiceService.generate_for_booking(b2)
    PaymentService.pay_online(actor=c2.user, method="CARD", invoice_id=inv2.id)
    c.invoice, c.booking = invoice, booking
    return c


class TestDashboards:
    def test_agency_dashboard_is_tenant_scoped(self, auth_client, shop, paid_booking):
        data = auth_client(shop.admin).get("/api/v1/reports/dashboard/").json()["data"]
        assert data["role"] == "AGENCY"
        assert Decimal(data["stats"]["revenue_today"]) == paid_booking.invoice.total  # B's payment excluded
        assert data["stats"]["customers"] == 1
        assert sum(Decimal(str(p["value"])) for p in data["charts"]["revenue"]) == paid_booking.invoice.total

    def test_agency_cannot_pick_another_organization(self, auth_client, shop, agency_b, paid_booking):
        data = auth_client(shop.admin).get(f"/api/v1/reports/dashboard/?organization={agency_b.org.id}").json()
        assert Decimal(data["data"]["stats"]["revenue_today"]) == paid_booking.invoice.total

    def test_super_admin_dashboard_and_filter(self, auth_client, super_admin, shop, agency_b, paid_booking):
        client = auth_client(super_admin)
        data = client.get("/api/v1/reports/dashboard/").json()["data"]
        assert data["role"] == "SUPER_ADMIN"
        assert Decimal(data["stats"]["revenue"]) > paid_booking.invoice.total  # both agencies
        assert {r["name"] for r in data["charts"]["agency_performance"]} == {shop.org.name, agency_b.org.name}
        only_a = client.get(f"/api/v1/reports/dashboard/?organization={shop.org.id}").json()["data"]
        assert Decimal(only_a["stats"]["revenue"]) == paid_booking.invoice.total

    def test_customer_dashboard(self, auth_client, paid_booking):
        data = auth_client(paid_booking.user).get("/api/v1/reports/dashboard/").json()["data"]
        assert data["role"] == "CUSTOMER"
        assert data["stats"]["vehicles"] == 1 and data["stats"]["services_completed"] == 1
        assert Decimal(data["stats"]["total_spent"]) == paid_booking.invoice.total
        assert Decimal(data["stats"]["pending_payments"]) == 0


class TestReports:
    def test_report_catalog_by_role(self, auth_client, super_admin, shop):
        admin_reports = {r["name"] for r in auth_client(super_admin).get("/api/v1/reports/").json()["data"]}
        agency_reports = {r["name"] for r in auth_client(shop.admin).get("/api/v1/reports/").json()["data"]}
        assert "agency-revenue" in admin_reports and "agency-revenue" not in agency_reports
        assert {"daily-revenue", "staff-performance", "customer-retention"} <= agency_reports

    def test_report_permissions(self, auth_client, shop, customer):
        assert auth_client(customer).get("/api/v1/reports/").status_code == 403
        assert auth_client(shop.manager).get("/api/v1/reports/daily-revenue/").status_code == 403  # no REPORT_VIEW
        Membership.objects.filter(user=shop.manager).update(permissions=["REPORT_VIEW"])
        assert auth_client(shop.manager).get("/api/v1/reports/daily-revenue/").status_code == 200
        assert auth_client(shop.admin).get("/api/v1/reports/agency-revenue/").status_code == 403
        assert auth_client(shop.admin).get("/api/v1/reports/nope/").status_code == 404

    def test_service_revenue_scoped(self, auth_client, shop, paid_booking):
        rows = auth_client(shop.admin).get("/api/v1/reports/service-revenue/").json()["data"]["rows"]
        assert [r["service"] for r in rows] == ["General Service"]

    def test_super_admin_agency_revenue(self, auth_client, super_admin, shop, agency_b, paid_booking):
        rows = auth_client(super_admin).get("/api/v1/reports/agency-revenue/").json()["data"]["rows"]
        assert {r["agency"] for r in rows} == {shop.org.name, agency_b.org.name}

    def test_csv_and_xlsx_export(self, auth_client, shop, paid_booking):
        client = auth_client(shop.admin)
        csv_res = client.get("/api/v1/reports/daily-revenue/?export=csv")
        assert csv_res.status_code == 200 and csv_res["Content-Type"].startswith("text/csv")
        body = csv_res.content.decode()
        assert "Daily revenue" in body and "Built by Sahil Thakur" in body
        xlsx = client.get("/api/v1/reports/staff-performance/?export=xlsx")
        assert xlsx.status_code == 200 and xlsx.content[:2] == b"PK"

    def test_csv_injection_is_neutralised(self):
        from apps.reports.exporters import to_csv

        res = to_csv({"name": "x", "title": "X", "columns": ["name"], "rows": [{"name": "=HYPERLINK(1)"}],
                      "period": {"from": "a", "to": "b"}})
        assert "'=HYPERLINK" in res.content.decode()

    def test_invalid_dates(self, auth_client, shop):
        assert auth_client(shop.admin).get("/api/v1/reports/daily-revenue/?date_from=bad").status_code == 400


class TestSearchAndTimeline:
    def test_search_is_tenant_scoped(self, auth_client, shop, agency_b, paid_booking):
        number = paid_booking.booking.booking_number
        hits = auth_client(shop.admin).get(f"/api/v1/search/?q={number}").json()["data"]
        assert [b["title"] for b in hits["bookings"]] == [number]
        assert auth_client(agency_b.admin).get(f"/api/v1/search/?q={number}").json()["data"]["bookings"] == []
        reg = paid_booking.vehicle.registration_number
        assert auth_client(shop.admin).get(f"/api/v1/search/?q={reg}").json()["data"]["vehicles"][0]["title"] == reg
        inv = paid_booking.invoice.invoice_number
        assert auth_client(paid_booking.user).get(f"/api/v1/search/?q={inv}").json()["data"]["invoices"][0]["title"] \
            == inv
        assert auth_client(shop.admin).get("/api/v1/search/?q=a").status_code == 400

    def test_timeline_and_summary(self, auth_client, shop, agency_b, paid_booking):
        cid = paid_booking.profile.id
        events = auth_client(shop.admin).get(f"/api/v1/customers/{cid}/timeline/").json()["data"]
        types = {e["type"] for e in events}
        assert {"BOOKING_PENDING", "INVOICE_GENERATED", "PAYMENT_RECEIVED"} <= types
        summary = auth_client(shop.admin).get(f"/api/v1/customers/{cid}/summary/").json()["data"]
        assert Decimal(summary["total_spending"]) == paid_booking.invoice.total
        assert summary["completed_services"] == 1
        mine = auth_client(paid_booking.user).get("/api/v1/customers/me/timeline/").json()["data"]
        assert len(mine) == len(events)
        assert auth_client(agency_b.admin).get(f"/api/v1/customers/{cid}/timeline/").status_code == 404
