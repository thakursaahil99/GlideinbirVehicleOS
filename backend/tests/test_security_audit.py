"""
Phase 12 audit sweeps: authentication on every endpoint, cross-tenant access on
every tenant-owned object type, and query budgets for the main list endpoints.
"""
import pytest
from django.urls import URLPattern, URLResolver, get_resolver

from apps.bookings.models import Booking
from apps.bookings.services import BookingService
from apps.invoices.services import InvoiceService
from apps.inventory.models import Part
from apps.job_cards.models import JobCard
from apps.payments.models import Payment
from apps.vendors.models import Holiday, ServiceResource

from .conftest import at, next_weekday

pytestmark = pytest.mark.django_db

PUBLIC = {
    "/api/v1/health/", "/api/v1/auth/register/", "/api/v1/auth/register-agency/", "/api/v1/auth/login/",
    "/api/v1/auth/refresh/", "/api/v1/auth/password-reset/", "/api/v1/auth/password-reset/confirm/",
    "/api/v1/auth/verify-email/", "/api/v1/schema/", "/api/v1/docs/",
}


def _api_paths():
    """Every concrete (parameter-free) API route plus a dummy-id variant of detail routes."""
    out = set()

    def walk(patterns, prefix=""):
        for p in patterns:
            if isinstance(p, URLResolver):
                walk(p.url_patterns, prefix + str(p.pattern))
            elif isinstance(p, URLPattern):
                route = prefix + str(p.pattern)
                if not route.startswith("api/v1/") or "(?P<format>" in route or "\\.(?P" in route:
                    continue
                path = (route.replace("^", "").replace("$", "")
                        .replace("(?P<pk>[^/.]+)", "00000000-0000-0000-0000-000000000000")
                        .replace("<slug:name>", "daily-revenue"))
                if "(?P<" in path or "<" in path:
                    continue
                out.add("/" + path)

    walk(get_resolver().url_patterns)
    return sorted(out)


@pytest.mark.parametrize("path", [p for p in _api_paths() if p not in PUBLIC])
def test_every_private_endpoint_requires_authentication(api_client, path):
    res = api_client.get(path)
    assert res.status_code in (401, 405), f"{path} answered {res.status_code} to an anonymous request"
    if res.status_code == 401:
        assert res.json()["success"] is False


def test_route_sweep_covers_the_api():
    paths = _api_paths()
    for expected in ("/api/v1/bookings/", "/api/v1/invoices/", "/api/v1/job-cards/", "/api/v1/payments/",
                     "/api/v1/inventory/parts/", "/api/v1/reports/dashboard/", "/api/v1/search/"):
        assert expected in paths


@pytest.fixture
def agency_a_world(shop, booker, auth_client):
    """One of everything owned by agency A."""
    c = booker()
    booking = BookingService.create(actor=c.user, vehicle_id=c.vehicle.id, vendor_service_id=shop.offering.id,
                                    start_datetime=at(next_weekday(0), "09:00"))
    admin = auth_client(shop.admin)
    admin.post(f"/api/v1/bookings/{booking.id}/confirm/")
    admin.post(f"/api/v1/bookings/{booking.id}/receive-vehicle/")
    Booking.objects.filter(pk=booking.pk).update(status="COMPLETED")
    invoice = InvoiceService.generate_for_booking(booking, notify=False)
    payment = Payment.objects.create(organization=shop.org, invoice=invoice, customer=c.profile, amount=10,
                                     method="CASH", status="SUCCEEDED")
    return {
        "bookings": booking.id, "job-cards": JobCard.objects.get(booking=booking).id, "invoices": invoice.id,
        "payments": payment.id, "customers": c.profile.id, "vehicles": c.vehicle.id,
        "vendor-services": shop.offering.id,
        "inventory/parts": Part.objects.create(organization=shop.org, name="P", sku="P1").id,
        "agency/resources": ServiceResource.objects.create(organization=shop.org, name="Bay X",
                                                           resource_type="BAY").id,
        "agency/holidays": Holiday.objects.create(organization=shop.org, name="H", start_date="2030-01-01",
                                                  end_date="2030-01-01").id,
        "organizations": shop.org.id,
    }


@pytest.mark.parametrize("resource", ["bookings", "job-cards", "invoices", "payments", "customers", "vehicles",
                                      "vendor-services", "inventory/parts", "agency/resources", "agency/holidays",
                                      "organizations"])
def test_agency_b_cannot_read_or_write_any_agency_a_object(auth_client, agency_a_world, agency_b, resource):
    client = auth_client(agency_b.admin)
    url = f"/api/v1/{resource}/{agency_a_world[resource]}/"
    assert client.get(url).status_code in (403, 404)
    assert client.patch(url, {"notes": "x", "name": "x"}).status_code in (403, 404, 405)
    assert client.delete(url).status_code in (403, 404, 405)


@pytest.mark.parametrize("resource", ["bookings", "job-cards", "invoices", "payments", "vehicles"])
def test_other_customer_cannot_see_customer_objects(auth_client, agency_a_world, booker, resource):
    stranger = booker()
    assert auth_client(stranger.user).get(f"/api/v1/{resource}/{agency_a_world[resource]}/").status_code == 404


class TestQueryBudgets:
    """Lists must not grow queries per row (N+1)."""

    @pytest.fixture
    def many_bookings(self, shop, booker):
        shop.offering.capacity = 10
        shop.offering.save()
        for t in ("09:00", "11:00", "14:00", "16:00"):
            for _ in range(2):
                c = booker()
                BookingService.create(actor=c.user, vehicle_id=c.vehicle.id, vendor_service_id=shop.offering.id,
                                      start_datetime=at(next_weekday(0), t))
        return shop

    @pytest.mark.parametrize("path,budget", [
        ("/api/v1/bookings/", 14), ("/api/v1/customers/", 10), ("/api/v1/vehicles/", 10),
        ("/api/v1/invoices/", 10), ("/api/v1/job-cards/", 10), ("/api/v1/bookings/calendar/?start=2000-01-01T00:00:00Z&end=2000-02-01T00:00:00Z", 10),
    ])
    def test_list_query_budget(self, auth_client, many_bookings, django_assert_max_num_queries, path, budget):
        client = auth_client(many_bookings.admin)
        with django_assert_max_num_queries(budget):
            res = client.get(path)
        assert res.status_code == 200

    def test_dashboard_budget(self, auth_client, many_bookings, django_assert_max_num_queries):
        client = auth_client(many_bookings.admin)
        with django_assert_max_num_queries(40):
            assert client.get("/api/v1/reports/dashboard/").status_code == 200


def test_api_security_headers(auth_client, customer):
    res = auth_client(customer).get("/api/v1/auth/me/")
    assert res["Content-Security-Policy"].startswith("default-src 'none'")
    assert res["Cache-Control"] == "no-store"
    assert "camera=()" in res["Permissions-Policy"]
    assert res["X-Frame-Options"] == "DENY"


def test_docs_keep_their_own_csp(api_client):
    assert "Content-Security-Policy" not in api_client.get("/api/v1/docs/")


def test_payment_endpoints_have_their_own_throttle(auth_client, customer, monkeypatch):
    from rest_framework.throttling import ScopedRateThrottle

    monkeypatch.setattr(ScopedRateThrottle, "THROTTLE_RATES", {"payments": "2/min", "search": "100/min"})
    client = auth_client(customer)
    codes = [client.post("/api/v1/payments/pay/", {"invoice": "00000000-0000-0000-0000-000000000000",
                                                   "method": "UPI"}).status_code for _ in range(3)]
    assert codes[:2] == [404, 404] and codes[2] == 429
    assert client.get("/api/v1/payments/").status_code == 200  # reads are not throttled by this scope
