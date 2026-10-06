"""Showroom catalogue: vehicle models, stock and sales — tenant-isolated, stock-safe."""
import pytest

from apps.vehicles.models import VehicleModel, VehicleSale

pytestmark = pytest.mark.django_db

MODELS = "/api/v1/showroom/models/"
SALES = "/api/v1/showroom/sales/"


def new_model(client, **extra):
    res = client.post(MODELS, {"vehicle_type": "SCOOTER", "brand": "TVS", "name": "Jupiter 125", "variant": "Disc",
                               "ex_showroom_price": "89000", "stock_quantity": 2, **extra})
    assert res.status_code == 201, res.content
    return res.json()["data"]


def sale(client, model_id, **extra):
    return client.post(SALES, {"vehicle_model": model_id, "buyer_name": "Ravi Kumar", "buyer_phone": "+919811122233",
                               "sale_price": "91000", "sold_on": "2026-10-06", "chassis_number": "MD626XYZ", **extra})


def test_add_edit_sell_and_cancel(auth_client, agency_a):
    client = auth_client(agency_a.admin)
    m = new_model(client)
    assert client.patch(f"{MODELS}{m['id']}/", {"colours": "Red, Blue"}).json()["data"]["colours"] == "Red, Blue"
    res = sale(client, m["id"])
    assert res.status_code == 201, res.content
    s = res.json()["data"]
    assert s["buyer_name"] == "Ravi Kumar" and s["sold_by_name"] == agency_a.admin.full_name
    assert VehicleModel.objects.get(pk=m["id"]).stock_quantity == 1
    assert client.patch(f"{SALES}{s['id']}/", {"registration_number": "MH12AB1234"}).status_code == 200
    assert client.delete(f"{SALES}{s['id']}/").status_code == 204
    assert VehicleModel.objects.get(pk=m["id"]).stock_quantity == 2


def test_cannot_sell_out_of_stock(auth_client, agency_a):
    client = auth_client(agency_a.admin)
    m = new_model(client, stock_quantity=1)
    assert sale(client, m["id"]).status_code == 201
    assert sale(client, m["id"]).status_code in (400, 409, 422)
    assert VehicleSale.objects.count() == 1


def test_stock_adjust(auth_client, agency_a):
    client = auth_client(agency_a.manager)
    m = new_model(client)
    assert client.post(f"{MODELS}{m['id']}/stock/", {"quantity": 5}).json()["data"]["stock_quantity"] == 7
    assert client.post(f"{MODELS}{m['id']}/stock/", {"quantity": -10}).status_code in (400, 409, 422)


def test_tenant_isolation(auth_client, agency_a, agency_b):
    m = new_model(auth_client(agency_a.admin))
    other = auth_client(agency_b.admin)
    assert other.get(f"{MODELS}{m['id']}/").status_code == 404
    assert sale(other, m["id"]).status_code == 400
    assert other.get(MODELS).json()["data"] == [] or not other.get(MODELS).json()["data"].get("results")


def test_staff_read_only(auth_client, agency_a):
    m = new_model(auth_client(agency_a.admin))
    staff = auth_client(agency_a.staff)
    assert staff.get(MODELS).status_code == 200
    assert staff.patch(f"{MODELS}{m['id']}/", {"colours": "X"}).status_code == 403
    assert sale(staff, m["id"]).status_code == 403
