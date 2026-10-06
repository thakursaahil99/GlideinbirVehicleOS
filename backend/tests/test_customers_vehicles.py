import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.accounts.constants import Role
from apps.audit_logs.models import AuditAction, AuditLog
from apps.customers.models import AgencyCustomer, Customer, CustomerNote
from apps.organizations.models import Membership
from apps.vehicles.models import Vehicle

from .conftest import PASSWORD

pytestmark = pytest.mark.django_db

CUSTOMERS = "/api/v1/customers/"
VEHICLES = "/api/v1/vehicles/"


class TestCustomerProfiles:
    def test_registration_creates_customer_profile(self, api_client):
        api_client.post("/api/v1/auth/register/", {"email": "c@e.com", "password": PASSWORD, "full_name": "Cee",
                                                   "phone": "+919811111111"})
        profile = Customer.objects.get(user__email="c@e.com")
        assert profile.full_name == "Cee" and profile.phone == "+919811111111"

    def test_customer_me_get_and_patch(self, auth_client, customer):
        client = auth_client(customer)
        assert client.get(f"{CUSTOMERS}me/").json()["data"]["full_name"] == customer.full_name
        res = client.patch(f"{CUSTOMERS}me/", {"city": "Pune", "full_name": "New Name"})
        assert res.status_code == 200
        customer.refresh_from_db()
        assert customer.full_name == "New Name"  # login account kept in sync
        assert client.patch(f"{CUSTOMERS}me/", {"email": "x@y.com"}).status_code == 403

    def test_profile_update_syncs_customer(self, auth_client, customer):
        auth_client(customer).patch("/api/v1/auth/me/", {"full_name": "Renamed Person"})
        assert Customer.objects.get(user=customer).full_name == "Renamed Person"

    def test_customer_cannot_list_customers(self, auth_client, customer):
        assert auth_client(customer).get(CUSTOMERS).status_code == 403


class TestCustomerTenantIsolation:
    def test_agency_sees_only_linked_customers(self, auth_client, agency_a, agency_b, make_customer):
        mine = make_customer(agency_a)
        theirs = make_customer(agency_b)
        shared = make_customer(agency_a, agency_b)
        make_customer()  # unlinked
        res = auth_client(agency_a.admin).get(CUSTOMERS)
        assert res.status_code == 200
        ids = {c["id"] for c in res.json()["data"]}
        assert ids == {str(mine.id), str(shared.id)}
        assert str(theirs.id) not in ids

    def test_agency_a_requests_agency_b_customer_gets_404(self, auth_client, agency_a, agency_b, make_customer):
        theirs = make_customer(agency_b)
        client = auth_client(agency_a.admin)
        assert client.get(f"{CUSTOMERS}{theirs.id}/").status_code == 404
        assert client.patch(f"{CUSTOMERS}{theirs.id}/", {"city": "X"}).status_code == 404
        assert client.get(f"{CUSTOMERS}{theirs.id}/notes/").status_code == 404

    def test_internal_notes_are_tenant_private(self, auth_client, agency_a, agency_b, make_customer):
        shared = make_customer(agency_a, agency_b)
        res = auth_client(agency_a.admin).post(f"{CUSTOMERS}{shared.id}/notes/", {"body": "Prefers mornings"})
        assert res.status_code == 201
        b_notes = auth_client(agency_b.admin).get(f"{CUSTOMERS}{shared.id}/notes/").json()["data"]
        assert b_notes == []
        a_notes = auth_client(agency_a.staff).get(f"{CUSTOMERS}{shared.id}/notes/").json()["data"]
        assert [n["body"] for n in a_notes] == ["Prefers mornings"]

    def test_customer_cannot_read_internal_notes(self, auth_client, customer, agency_a):
        profile = Customer.objects.get(user=customer)
        CustomerNote.objects.create(customer=profile, organization=agency_a.org, body="secret")
        assert auth_client(customer).get(f"{CUSTOMERS}{profile.id}/notes/").status_code == 403

    def test_search_by_vehicle_registration(self, auth_client, agency_a, make_customer, make_vehicle):
        c = make_customer(agency_a, full_name="Searchable Person")
        make_vehicle(c, registration_number="KA01XY9999")
        make_customer(agency_a)
        res = auth_client(agency_a.admin).get(f"{CUSTOMERS}?search=KA01XY")
        assert [r["id"] for r in res.json()["data"]] == [str(c.id)]


class TestWalkInCustomers:
    def test_agency_creates_and_edits_walk_in(self, auth_client, agency_a):
        client = auth_client(agency_a.admin)
        res = client.post(CUSTOMERS, {"full_name": "Walk In", "phone": "+919822222222", "city": "Pune"})
        assert res.status_code == 201, res.json()
        data = res.json()["data"]
        assert data["is_walk_in"] and data["can_edit"]
        assert AgencyCustomer.objects.filter(organization=agency_a.org, customer_id=data["id"],
                                             source="WALK_IN").exists()
        assert client.patch(f"{CUSTOMERS}{data['id']}/", {"city": "Mumbai"}).status_code == 200
        assert AuditLog.objects.filter(action=AuditAction.CUSTOMER_UPDATED).exists()

    def test_agency_cannot_edit_self_registered_customer(self, auth_client, agency_a, make_customer):
        c = make_customer(agency_a)
        res = auth_client(agency_a.admin).patch(f"{CUSTOMERS}{c.id}/", {"full_name": "Changed"})
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "CUSTOMER_SELF_MANAGED"

    def test_staff_permissions_enforced(self, auth_client, agency_a):
        # Fixture staff has CUSTOMER_VIEW but not CUSTOMER_CREATE; fixture manager has no codes.
        assert auth_client(agency_a.staff).get(CUSTOMERS).status_code == 200
        assert auth_client(agency_a.staff).post(CUSTOMERS, {"full_name": "X", "phone": "+919800000001"}).status_code == 403
        assert auth_client(agency_a.manager).get(CUSTOMERS).status_code == 403
        Membership.objects.filter(user=agency_a.manager).update(permissions=["CUSTOMER_VIEW", "CUSTOMER_CREATE"])
        assert auth_client(agency_a.manager).post(CUSTOMERS, {"full_name": "X", "phone": "+919800000001"}).status_code == 201

    def test_super_admin_lists_all(self, auth_client, super_admin, agency_a, agency_b, make_customer):
        make_customer(agency_a)
        make_customer(agency_b)
        assert auth_client(super_admin).get(CUSTOMERS).json()["meta"]["pagination"]["count"] == 2


class TestVehicles:
    payload = {"vehicle_type": "CAR", "brand": "Hyundai", "model": "Creta", "registration_number": "mh 12-ab 1234",
               "fuel_type": "PETROL", "manufacturing_year": 2022}

    def test_customer_adds_own_vehicle_and_registration_is_normalized(self, auth_client, customer):
        res = auth_client(customer).post(VEHICLES, self.payload)
        assert res.status_code == 201, res.json()
        assert res.json()["data"]["registration_number"] == "MH12AB1234"
        assert Vehicle.objects.get().customer.user == customer

    def test_customer_cannot_assign_vehicle_to_someone_else(self, auth_client, customer, make_customer):
        other = make_customer()
        res = auth_client(customer).post(VEHICLES, {**self.payload, "customer": str(other.id)})
        assert res.status_code == 201
        assert Vehicle.objects.get().customer.user == customer

    def test_duplicate_registration_rejected(self, auth_client, customer):
        client = auth_client(customer)
        client.post(VEHICLES, self.payload)
        res = client.post(VEHICLES, {**self.payload, "registration_number": "MH12AB1234"})
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "DUPLICATE_VEHICLE"

    def test_validation(self, auth_client, customer):
        client = auth_client(customer)
        assert client.post(VEHICLES, {**self.payload, "vin": "SHORT"}).status_code == 400
        assert client.post(VEHICLES, {**self.payload, "manufacturing_year": 2999}).status_code == 400
        assert client.post(VEHICLES, {**self.payload, "vehicle_type": "EV", "fuel_type": "DIESEL"}).status_code == 400

    def test_customers_only_see_own_vehicles(self, auth_client, customer, make_customer, make_vehicle):
        mine = make_vehicle(Customer.objects.get(user=customer))
        other = make_vehicle(make_customer())
        client = auth_client(customer)
        assert [v["id"] for v in client.get(VEHICLES).json()["data"]] == [str(mine.id)]
        assert client.get(f"{VEHICLES}{other.id}/").status_code == 404
        assert client.patch(f"{VEHICLES}{other.id}/", {"color": "Red"}).status_code == 404

    def test_agency_sees_only_linked_customer_vehicles(self, auth_client, agency_a, agency_b, make_customer,
                                                       make_vehicle):
        a_vehicle = make_vehicle(make_customer(agency_a))
        b_vehicle = make_vehicle(make_customer(agency_b))
        client = auth_client(agency_a.staff)
        ids = [v["id"] for v in client.get(VEHICLES).json()["data"]]
        assert ids == [str(a_vehicle.id)]
        assert client.get(f"{VEHICLES}{b_vehicle.id}/").status_code == 404

    def test_agency_adds_vehicle_only_for_linked_customer(self, auth_client, agency_a, agency_b, make_customer):
        Membership.objects.filter(user=agency_a.manager).update(permissions=["VEHICLE_VIEW", "VEHICLE_CREATE"])
        client = auth_client(agency_a.manager)
        walk_in = auth_client(agency_a.admin).post(CUSTOMERS, {"full_name": "W", "phone": "+919833333333"}).json()["data"]
        assert client.post(VEHICLES, {**self.payload, "customer": walk_in["id"]}).status_code == 201
        foreign = make_customer(agency_b)
        res = client.post(VEHICLES, {**self.payload, "customer": str(foreign.id)})
        assert res.status_code == 404
        assert client.post(VEHICLES, self.payload).status_code == 400  # customer required

    def test_agency_cannot_edit_self_registered_customers_vehicle(self, auth_client, agency_a, make_customer,
                                                                  make_vehicle):
        v = make_vehicle(make_customer(agency_a))
        res = auth_client(agency_a.admin).patch(f"{VEHICLES}{v.id}/", {"color": "Blue"})
        assert res.status_code == 403

    def test_archive_keeps_history(self, auth_client, customer, make_vehicle):
        v = make_vehicle(Customer.objects.get(user=customer))
        client = auth_client(customer)
        assert client.delete(f"{VEHICLES}{v.id}/").status_code == 204
        v.refresh_from_db()
        assert v.is_active is False
        assert client.get(VEHICLES).json()["data"] == []
        assert len(client.get(f"{VEHICLES}?is_active=false").json()["data"]) == 1
        # Archived plate can be re-registered.
        assert client.post(VEHICLES, {**self.payload, "registration_number": v.registration_number}).status_code == 201

    def test_document_upload_validation(self, auth_client, customer, make_vehicle):
        v = make_vehicle(Customer.objects.get(user=customer))
        client = auth_client(customer)
        pdf = SimpleUploadedFile("rc.pdf", b"%PDF-1.4 fake but has magic", content_type="application/pdf")
        res = client.post(f"{VEHICLES}{v.id}/documents/", {"kind": "RC", "file": pdf}, format="multipart")
        assert res.status_code == 201, res.json()
        fake = SimpleUploadedFile("rc.pdf", b"MZ executable", content_type="application/pdf")
        assert client.post(f"{VEHICLES}{v.id}/documents/", {"kind": "RC", "file": fake},
                           format="multipart").status_code == 400
        exe = SimpleUploadedFile("virus.exe", b"MZ", content_type="application/octet-stream")
        assert client.post(f"{VEHICLES}{v.id}/documents/", {"file": exe}, format="multipart").status_code == 400
        buf = io.BytesIO()
        Image.new("RGB", (100, 80)).save(buf, format="JPEG")
        photo = SimpleUploadedFile("front.jpg", buf.getvalue(), content_type="image/jpeg")
        assert client.post(f"{VEHICLES}{v.id}/documents/", {"kind": "PHOTO", "file": photo},
                           format="multipart").status_code == 201
        assert len(client.get(f"{VEHICLES}{v.id}/documents/").json()["data"]) == 2

    def test_other_customer_cannot_touch_documents(self, auth_client, customer, make_customer, make_vehicle):
        v = make_vehicle(make_customer())
        assert auth_client(customer).get(f"{VEHICLES}{v.id}/documents/").status_code == 404

    def test_role_without_vehicle_perms(self, auth_client, agency_a):
        assert auth_client(agency_a.manager).get(VEHICLES).status_code == 403
