"""Inventory catalogue: categories, suppliers, vehicle fitments and the stock summary."""

from decimal import Decimal

import pytest

from apps.inventory.models import Part, PartCategory, PartFitment, StockTransaction, Supplier

pytestmark = pytest.mark.django_db

PARTS = "/api/v1/inventory/parts/"
CATEGORIES = "/api/v1/inventory/categories/"
SUPPLIERS = "/api/v1/inventory/suppliers/"


def items(res):
    data = res.json()["data"]
    return data["items"] if isinstance(data, dict) and "items" in data else data


@pytest.fixture
def catalog(agency_a):
    org = agency_a.org
    brakes = PartCategory.objects.create(organization=org, name="Brakes")
    dealer = Supplier.objects.create(organization=org, name="Sharma Auto Parts")
    pad = Part.objects.create(organization=org, name="Brake shoe", sku="BS-ACT", category=brakes,
                              stock_quantity=6, minimum_stock=2, purchase_price=150, selling_price=250)
    PartFitment.objects.create(organization=org, part=pad, vehicle_type="SCOOTER", brand="Honda", model="Activa 6G")
    plug = Part.objects.create(organization=org, name="Spark plug", sku="SP-HON", stock_quantity=0, minimum_stock=2)
    PartFitment.objects.create(organization=org, part=plug, brand="Honda")  # every Honda model
    chain = Part.objects.create(organization=org, name="Chain kit", sku="CK-SPL", stock_quantity=1, minimum_stock=3)
    PartFitment.objects.create(organization=org, part=chain, vehicle_type="BIKE", brand="Hero", model="Splendor",
                               year_from=2015, year_to=2019)
    bulb = Part.objects.create(organization=org, name="H4 bulb", sku="BULB-H4", universal=True, stock_quantity=20)
    return {"org": org, "brakes": brakes, "dealer": dealer, "pad": pad, "plug": plug, "chain": chain, "bulb": bulb}


class TestFitmentLookup:
    def test_scooter_model_lists_matching_parts_with_stock_status(self, auth_client, agency_a, catalog):
        res = auth_client(agency_a.staff).get(PARTS + "compatible/",
                                              {"vehicle_type": "SCOOTER", "brand": "honda", "model": "activa 6g"})
        assert res.status_code == 200, res.json()
        found = {p["sku"]: p["stock_status"] for p in items(res)}
        # Exact model, brand-wide fitment and universal parts; never the Hero chain.
        assert found == {"BS-ACT": "IN_STOCK", "SP-HON": "OUT_OF_STOCK", "BULB-H4": "IN_STOCK"}

    def test_year_bounds_and_type_are_respected(self, auth_client, agency_a, catalog):
        client = auth_client(agency_a.staff)
        in_range = items(client.get(PARTS + "compatible/", {"brand": "Hero", "model": "Splendor", "year": 2017}))
        assert {p["sku"] for p in in_range} == {"CK-SPL", "BULB-H4"}
        assert in_range[0]["stock_status"] in ("LOW_STOCK", "IN_STOCK")
        too_new = items(client.get(PARTS + "compatible/", {"brand": "Hero", "model": "Splendor", "year": 2022}))
        assert {p["sku"] for p in too_new} == {"BULB-H4"}
        wrong_type = items(client.get(PARTS + "compatible/", {"brand": "Hero", "model": "Splendor",
                                                              "vehicle_type": "CAR"}))
        assert {p["sku"] for p in wrong_type} == {"BULB-H4"}

    def test_stock_status_filter_on_lookup(self, auth_client, agency_a, catalog):
        res = auth_client(agency_a.staff).get(PARTS + "compatible/", {"brand": "Honda", "model": "Activa 6G",
                                                                      "stock_status": "OUT_OF_STOCK"})
        assert [p["sku"] for p in items(res)] == ["SP-HON"]

    def test_lookup_by_vehicle_id(self, auth_client, agency_a, agency_b, catalog, make_customer, make_vehicle):
        profile = make_customer(agency_a)
        vehicle = make_vehicle(profile, brand="Honda", model="Activa 6G", vehicle_type="SCOOTER")
        res = auth_client(agency_a.staff).get(PARTS + "compatible/", {"vehicle": vehicle.id})
        assert res.status_code == 200, res.json()
        assert {p["sku"] for p in items(res)} == {"BS-ACT", "SP-HON", "BULB-H4"}
        # Customers can't browse agency stock, and another agency can't use this customer's vehicle.
        assert auth_client(profile.user).get(PARTS + "compatible/", {"vehicle": vehicle.id}).status_code == 403
        assert auth_client(agency_b.admin).get(PARTS + "compatible/", {"vehicle": vehicle.id}).status_code == 400

    def test_brand_is_required(self, auth_client, agency_a, catalog):
        res = auth_client(agency_a.staff).get(PARTS + "compatible/", {"model": "Activa"})
        assert res.status_code == 400

    def test_other_agency_parts_never_match(self, auth_client, agency_b, catalog):
        res = auth_client(agency_b.admin).get(PARTS + "compatible/", {"brand": "Honda", "model": "Activa 6G"})
        assert res.status_code == 200 and items(res) == []

    def test_fitment_options_for_picker(self, auth_client, agency_a, catalog):
        rows = auth_client(agency_a.staff).get(PARTS + "fitment-options/").json()["data"]
        assert {"vehicle_type": "SCOOTER", "brand": "Honda", "model": "Activa 6G", "parts": 1} in rows


class TestPartForm:
    def test_create_with_category_supplier_and_fitments(self, auth_client, agency_a, catalog):
        client = auth_client(agency_a.admin)
        res = client.post(PARTS, {
            "name": "Clutch plate", "sku": "cp-1", "category": str(catalog["brakes"].id),
            "preferred_supplier": str(catalog["dealer"].id), "hsn_code": "8708", "rack_location": "Rack B · Shelf 3",
            "fitments": [{"vehicle_type": "BIKE", "brand": " Bajaj ", "model": "Pulsar 150", "year_from": 2018}],
        }, format="json")
        assert res.status_code == 201, res.json()
        data = res.json()["data"]
        assert data["category_name"] == "Brakes" and data["preferred_supplier_name"] == "Sharma Auto Parts"
        assert data["fitments"][0]["brand"] == "Bajaj" and data["fitments"][0]["year_to"] is None

        # PATCH without fitments keeps them; an empty list clears them.
        url = f"{PARTS}{data['id']}/"
        assert len(client.patch(url, {"brand": "Valeo"}, format="json").json()["data"]["fitments"]) == 1
        assert client.patch(url, {"fitments": []}, format="json").json()["data"]["fitments"] == []

    def test_rejects_other_agency_category_and_bad_values(self, auth_client, agency_a, agency_b, catalog):
        foreign = PartCategory.objects.create(organization=agency_b.org, name="Foreign")
        client = auth_client(agency_a.admin)
        assert client.post(PARTS, {"name": "X", "sku": "X1", "category": str(foreign.id)},
                           format="json").status_code == 400
        assert client.post(PARTS, {"name": "X", "sku": "X2", "hsn_code": "87AB"}, format="json").status_code == 400
        bad_years = {"name": "X", "sku": "X3", "fitments": [{"brand": "TVS", "year_from": 2020, "year_to": 2010}]}
        assert client.post(PARTS, bad_years, format="json").status_code == 400

    def test_staff_cannot_edit_catalogue(self, auth_client, agency_a, catalog):
        staff = auth_client(agency_a.staff)
        assert staff.post(CATEGORIES, {"name": "Tyres"}).status_code == 403
        assert staff.post(SUPPLIERS, {"name": "Dealer"}).status_code == 403
        assert staff.get(CATEGORIES).status_code == 200


class TestSuppliers:
    def test_purchase_records_supplier_and_totals(self, auth_client, agency_a, catalog):
        client = auth_client(agency_a.admin)
        chain, dealer = catalog["chain"], catalog["dealer"]
        res = client.post(f"{PARTS}{chain.id}/move/", {"transaction_type": "PURCHASE", "quantity": "4",
                                                       "unit_price": "500", "supplier": str(dealer.id)})
        assert res.status_code == 201, res.json()
        assert res.json()["data"]["supplier_name"] == "Sharma Auto Parts"
        chain.refresh_from_db()
        assert chain.preferred_supplier_id == dealer.id  # first dealer becomes the default

        row = next(s for s in items(client.get(SUPPLIERS)) if s["id"] == str(dealer.id))
        assert row["purchase_count"] == 1 and Decimal(row["purchase_total"]) == Decimal("2000.00")
        assert row["parts_count"] == 1

    def test_supplier_only_on_purchases_and_same_agency(self, auth_client, agency_a, agency_b, catalog):
        client = auth_client(agency_a.admin)
        bulb = catalog["bulb"]
        sale = client.post(f"{PARTS}{bulb.id}/move/", {"transaction_type": "SALE", "quantity": "1",
                                                       "supplier": str(catalog["dealer"].id)})
        assert sale.status_code == 400
        foreign = Supplier.objects.create(organization=agency_b.org, name="Elsewhere")
        res = client.post(f"{PARTS}{bulb.id}/move/", {"transaction_type": "PURCHASE", "quantity": "1",
                                                      "supplier": str(foreign.id)})
        assert res.status_code == 400
        assert not StockTransaction.objects.filter(part=bulb).exists()

    def test_supplier_with_history_cannot_be_deleted(self, auth_client, agency_a, catalog):
        client = auth_client(agency_a.admin)
        dealer = catalog["dealer"]
        client.post(f"{PARTS}{catalog['bulb'].id}/move/", {"transaction_type": "PURCHASE", "quantity": "1",
                                                            "supplier": str(dealer.id)})
        assert client.delete(f"{SUPPLIERS}{dealer.id}/").status_code == 400
        spare = Supplier.objects.create(organization=agency_a.org, name="Unused")
        assert client.delete(f"{SUPPLIERS}{spare.id}/").status_code == 204

    def test_gstin_is_validated(self, auth_client, agency_a):
        client = auth_client(agency_a.admin)
        assert client.post(SUPPLIERS, {"name": "A", "gst_number": "123"}).status_code == 400
        assert client.post(SUPPLIERS, {"name": "B", "gst_number": "27aapfu0939f1zv"}).status_code == 201

    def test_agency_b_cannot_see_agency_a_suppliers(self, auth_client, agency_b, catalog):
        client = auth_client(agency_b.admin)
        assert items(client.get(SUPPLIERS)) == []
        assert client.get(f"{SUPPLIERS}{catalog['dealer'].id}/").status_code == 404
        assert client.get(f"{CATEGORIES}{catalog['brakes'].id}/").status_code == 404


class TestSummary:
    def test_values_counts_and_categories(self, auth_client, agency_a, catalog):
        data = auth_client(agency_a.staff).get(PARTS + "summary/").json()["data"]
        assert data["parts"] == 4
        assert Decimal(data["stock_value_cost"]) == Decimal("900.00")  # 6 brake shoes × ₹150
        assert data["out_of_stock"] == 1 and data["low_stock"] == 1
        assert {"category": "Brakes", "parts": 1, "value": "900.00"} in data["by_category"]

    def test_categories_list_counts_parts(self, auth_client, agency_a, catalog):
        rows = auth_client(agency_a.staff).get(CATEGORIES).json()["data"]
        assert {"name": "Brakes", "parts_count": 1} == {k: rows[0][k] for k in ("name", "parts_count")}
