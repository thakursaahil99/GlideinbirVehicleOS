from decimal import Decimal

import pytest

from apps.audit_logs.models import AuditAction, AuditLog
from apps.organizations.models import Membership, OrganizationStatus
from apps.services.models import Service, VendorService
from apps.vendors.models import ResourceType, ServiceResource

pytestmark = pytest.mark.django_db

SERVICES = "/api/v1/services/"
OFFERINGS = "/api/v1/vendor-services/"
VENDORS = "/api/v1/vendors/"


class TestCatalog:
    def test_catalog_is_seeded(self):
        slugs = set(Service.objects.values_list("slug", flat=True))
        assert {"general-service", "oil-change", "ev-service", "pickup-drop", "emergency-repair"} <= slugs
        assert Service.objects.count() >= 17

    def test_everyone_reads_active_services(self, auth_client, customer):
        Service.objects.filter(slug="car-wash").update(active=False)
        res = auth_client(customer).get(f"{SERVICES}?page_size=100")
        slugs = {s["slug"] for s in res.json()["data"]}
        assert "general-service" in slugs and "car-wash" not in slugs

    def test_filter_by_vehicle_type(self, auth_client, customer):
        res = auth_client(customer).get(f"{SERVICES}?vehicle_type=SCOOTER&page_size=100")
        for s in res.json()["data"]:
            assert "SCOOTER" in s["supported_vehicle_types"]
        assert "scooter-service" in {s["slug"] for s in res.json()["data"]}

    def test_only_super_admin_manages_catalog(self, auth_client, super_admin, agency_a):
        payload = {"name": "Ceramic Coating", "category": "CLEANING", "supported_vehicle_types": ["CAR"],
                   "default_duration": 300, "base_price": "9999.00"}
        assert auth_client(agency_a.admin).post(SERVICES, payload).status_code == 403
        res = auth_client(super_admin).post(SERVICES, payload)
        assert res.status_code == 201, res.json()
        assert res.json()["data"]["slug"] == "ceramic-coating"
        sid = res.json()["data"]["id"]
        assert auth_client(super_admin).patch(f"{SERVICES}{sid}/", {"base_price": "8999.00"}).status_code == 200
        assert AuditLog.objects.filter(action=AuditAction.SERVICE_PRICE_CHANGED, object_id=sid).count() == 2
        assert auth_client(super_admin).delete(f"{SERVICES}{sid}/").status_code == 405

    def test_catalog_validation(self, auth_client, super_admin):
        bad = {"name": "X", "category": "CLEANING", "supported_vehicle_types": ["PLANE"], "default_duration": 30,
               "base_price": "-1"}
        res = auth_client(super_admin).post(SERVICES, bad)
        assert res.status_code == 400
        assert {"supported_vehicle_types", "base_price"} <= res.json()["error"]["details"].keys()


class TestVendorOfferings:
    def test_admin_offers_service_with_own_price(self, auth_client, agency_a):
        general = Service.objects.get(slug="general-service")
        res = auth_client(agency_a.admin).post(OFFERINGS, {"service": str(general.id), "custom_price": "2999.00",
                                                           "custom_duration": 150, "capacity": 2})
        assert res.status_code == 201, res.json()
        data = res.json()["data"]
        assert data["price"] == "2999.00" and data["duration"] == 150 and data["tax_rate"] == "18.00"
        assert AuditLog.objects.filter(action=AuditAction.SERVICE_PRICE_CHANGED, organization=agency_a.org).exists()

    def test_defaults_fall_back_to_catalog(self, make_offering, agency_a):
        offering = make_offering(agency_a)
        assert offering.price == Decimal("3499.00") and offering.duration == 180

    def test_cannot_offer_twice_or_inactive(self, auth_client, agency_a, make_offering):
        make_offering(agency_a, "oil-change")
        oil = Service.objects.get(slug="oil-change")
        res = auth_client(agency_a.admin).post(OFFERINGS, {"service": str(oil.id)})
        assert res.status_code == 400 and res.json()["error"]["code"] == "SERVICE_ALREADY_OFFERED"
        Service.objects.filter(slug="car-wash").update(active=False)
        wash = Service.objects.get(slug="car-wash")
        res = auth_client(agency_a.admin).post(OFFERINGS, {"service": str(wash.id)})
        assert res.json()["error"]["code"] == "SERVICE_INACTIVE"

    def test_price_change_is_audited_with_old_and_new(self, auth_client, agency_a, make_offering):
        offering = make_offering(agency_a, custom_price=Decimal("1000"))
        res = auth_client(agency_a.admin).patch(f"{OFFERINGS}{offering.id}/", {"custom_price": "1200.00"})
        assert res.status_code == 200
        log = AuditLog.objects.filter(action=AuditAction.SERVICE_PRICE_CHANGED).latest("created_at")
        assert log.old_data == {"custom_price": "1000.00"} and log.new_data == {"custom_price": "1200.00"}

    def test_service_cannot_be_switched_on_update(self, auth_client, agency_a, make_offering):
        offering = make_offering(agency_a)
        other = Service.objects.get(slug="car-wash")
        auth_client(agency_a.admin).patch(f"{OFFERINGS}{offering.id}/", {"service": str(other.id)})
        offering.refresh_from_db()
        assert offering.service.slug == "general-service"

    def test_required_resource_type_needs_resources(self, auth_client, agency_a):
        general = Service.objects.get(slug="general-service")
        payload = {"service": str(general.id), "required_resource_type": "BAY"}
        res = auth_client(agency_a.admin).post(OFFERINGS, payload)
        assert res.status_code == 400 and res.json()["error"]["code"] == "NO_RESOURCES_OF_TYPE"
        ServiceResource.objects.create(organization=agency_a.org, name="Bay 1", resource_type=ResourceType.BAY)
        assert auth_client(agency_a.admin).post(OFFERINGS, payload).status_code == 201

    def test_service_manage_permission(self, auth_client, agency_a):
        oil = Service.objects.get(slug="oil-change")
        assert auth_client(agency_a.manager).post(OFFERINGS, {"service": str(oil.id)}).status_code == 403
        Membership.objects.filter(user=agency_a.manager).update(permissions=["SERVICE_MANAGE"])
        assert auth_client(agency_a.manager).post(OFFERINGS, {"service": str(oil.id)}).status_code == 201
        assert auth_client(agency_a.staff).get(OFFERINGS).status_code == 200

    def test_offerings_are_tenant_scoped(self, auth_client, agency_a, agency_b, make_offering):
        theirs = make_offering(agency_b)
        client = auth_client(agency_a.admin)
        assert client.get(OFFERINGS).json()["data"] == []
        assert client.get(f"{OFFERINGS}{theirs.id}/").status_code == 404
        assert client.patch(f"{OFFERINGS}{theirs.id}/", {"custom_price": "1"}).status_code == 404
        assert client.delete(f"{OFFERINGS}{theirs.id}/").status_code == 404
        theirs.refresh_from_db()
        assert theirs.custom_price is None

    def test_customer_cannot_manage_offerings(self, auth_client, customer):
        assert auth_client(customer).get(OFFERINGS).status_code == 403


class TestVendorComparison:
    def test_directory_filtered_by_service_shows_prices(self, auth_client, customer, make_agency, make_offering):
        cheap, pricey, none_ = make_agency("Cheap Garage"), make_agency("Pricey Garage"), make_agency("No Oil")
        make_offering(cheap, "oil-change", custom_price=Decimal("900"))
        make_offering(pricey, "oil-change", custom_price=Decimal("1800"))
        make_offering(none_, "car-wash")
        res = auth_client(customer).get(f"{VENDORS}?service=oil-change&ordering=price")
        rows = res.json()["data"]
        assert [r["name"] for r in rows] == ["Cheap Garage", "Pricey Garage"]
        assert rows[0]["offer_price"] == "900.00" and rows[0]["offer_duration"] == 45
        res = auth_client(customer).get(f"{VENDORS}?service=oil-change&ordering=-price")
        assert [r["name"] for r in res.json()["data"]] == ["Pricey Garage", "Cheap Garage"]

    def test_inactive_or_disabled_offerings_excluded(self, auth_client, customer, make_agency, make_offering):
        a, b, c = make_agency("A1"), make_agency("B1"), make_agency("C1", status=OrganizationStatus.SUSPENDED)
        make_offering(a, "oil-change", active=False)
        make_offering(b, "oil-change", online_booking_enabled=False)
        make_offering(c, "oil-change")
        assert auth_client(customer).get(f"{VENDORS}?service=oil-change").json()["data"] == []

    def test_vehicle_type_filter(self, auth_client, customer, make_agency, make_offering):
        ev_shop, bike_shop = make_agency("EV Shop"), make_agency("Bike Shop")
        make_offering(ev_shop, "ev-service")
        make_offering(bike_shop, "bike-service")
        names = [r["name"] for r in auth_client(customer).get(f"{VENDORS}?vehicle_type=EV").json()["data"]]
        assert names == ["EV Shop"]

    def test_vendor_services_endpoint(self, auth_client, customer, agency_a, make_offering):
        make_offering(agency_a, "oil-change", custom_price=Decimal("1100"))
        make_offering(agency_a, "car-wash", active=False)
        res = auth_client(customer).get(f"{VENDORS}{agency_a.org.id}/services/")
        assert res.status_code == 200
        rows = res.json()["data"]
        assert [r["service"]["slug"] for r in rows] == ["oil-change"]
        assert rows[0]["price"] == "1100.00"
        assert "capacity" not in rows[0]  # internal capacity isn't public

    def test_protected_delete_returns_conflict(self, auth_client, agency_a, make_offering):
        offering = make_offering(agency_a)
        assert auth_client(agency_a.admin).delete(f"{OFFERINGS}{offering.id}/").status_code == 204
        assert not VendorService.objects.filter(pk=offering.pk).exists()
