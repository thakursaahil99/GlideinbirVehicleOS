"""Bulk import from CSV / Excel / PDF, and Super Admin adding parts for an agency."""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import Workbook

from apps.customers.models import Customer
from apps.inventory.models import Part, StockTransaction
from apps.vehicles.models import Vehicle

pytestmark = pytest.mark.django_db

PARTS_CSV = (
    "Part Name,Part No,Brand,Category,Dealer,MRP,Cost,Qty,Fits vehicles\n"
    'Disc brake pad,DBP-PUL,Brembo,Brakes,Sharma Auto Parts,"₹1,250",800,6,BIKE: Bajaj / Pulsar 150 / 2018-2024\n'
    "Bad row,,X,,,,,,\n"
    "Horn 12V,HORN-12,Minda,Electrical,,350,200,15,Honda / Activa 6G; TVS / Jupiter\n"
)


def upload(client, resource, name, content, dry_run, **extra):
    file = SimpleUploadedFile(name, content if isinstance(content, bytes) else content.encode())
    return client.post(f"/api/v1/imports/{resource}/", {"file": file, "dry_run": str(dry_run).lower(), **extra},
                       format="multipart")


def test_dry_run_reports_without_writing(auth_client, agency_a):
    res = upload(auth_client(agency_a.admin), "parts", "parts.csv", PARTS_CSV, True)
    assert res.status_code == 200, res.json()
    data = res.json()["data"]
    assert (data["created"], data["errors"]) == (2, [{"row": 3, "message": "Missing SKU."}])
    assert not Part.objects.filter(organization=agency_a.org).exists()


def test_import_creates_parts_with_fitments_and_opening_stock(auth_client, agency_a):
    data = upload(auth_client(agency_a.admin), "parts", "parts.csv", PARTS_CSV, False).json()["data"]
    assert data["created"] == 2
    pad = Part.objects.get(organization=agency_a.org, sku="DBP-PUL")
    assert pad.selling_price == 1250 and pad.category.name == "Brakes" and pad.preferred_supplier.name == "Sharma Auto Parts"
    assert pad.stock_quantity == 6 and StockTransaction.objects.filter(part=pad, transaction_type="PURCHASE").count() == 1
    fit = pad.fitments.get()
    assert (fit.vehicle_type, fit.brand, fit.model, fit.year_from, fit.year_to) == ("BIKE", "Bajaj", "Pulsar 150", 2018, 2024)
    assert Part.objects.get(sku="HORN-12").fitments.count() == 2
    # Re-importing the same SKUs updates prices instead of duplicating.
    again = upload(auth_client(agency_a.admin), "parts", "parts.csv", PARTS_CSV.replace("350,200", "399,200"), False)
    assert again.json()["data"]["updated"] == 2 and Part.objects.get(sku="HORN-12").selling_price == 399


def test_excel_customers_then_vehicles(auth_client, agency_a):
    client = auth_client(agency_a.admin)
    wb = Workbook()
    wb.active.append(["Name", "Mobile", "City"])
    wb.active.append(["Riya Kapoor", "+91 98111 22233", "Pune"])
    wb.active.append(["Riya Kapoor", "+919811122233", "Pune"])  # duplicate phone → skipped
    buf = io.BytesIO()
    wb.save(buf)
    data = upload(client, "customers", "c.xlsx", buf.getvalue(), False).json()["data"]
    assert (data["created"], data["skipped"]) == (1, 1)
    vehicles = "Customer phone,Registration no.,Type,Brand,Model,Year\n+919811122233,mh12 ab 1234,Scooty,Honda,Activa 6G,2022\n+910000000000,MH12ZZ9999,BIKE,Hero,Splendor,2019\n"
    data = upload(client, "vehicles", "v.csv", vehicles, False).json()["data"]
    assert data["created"] == 1 and "No customer" in data["errors"][0]["message"]
    v = Vehicle.objects.get(registration_number="MH12AB1234")
    assert v.vehicle_type == "SCOOTER" and v.customer == Customer.objects.get(phone="+919811122233")


def test_pdf_table(auth_client, agency_a):
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Table

    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4).build([Table([["Name", "GSTIN", "Phone"], ["Moto Spares", "", "+919898765432"]],
                                                     style=[("GRID", (0, 0), (-1, -1), 0.5, "black")])])
    data = upload(auth_client(agency_a.admin), "suppliers", "s.pdf", buf.getvalue(), False).json()["data"]
    assert data["created"] == 1, data


def test_permissions_and_tenancy(auth_client, agency_a, super_admin):
    assert upload(auth_client(agency_a.staff), "parts", "p.csv", PARTS_CSV, True).status_code == 403
    # Staff hold CUSTOMER_CREATE by default, so they may import customers.
    assert upload(auth_client(agency_a.staff), "customers", "c.csv", "Name,Phone\nA,+919800000099\n", True).status_code == 200
    sa = auth_client(super_admin)
    assert upload(sa, "parts", "p.csv", PARTS_CSV, False).status_code == 400  # must choose an agency
    res = upload(sa, "parts", "p.csv", PARTS_CSV, False, organization=str(agency_a.org.id))
    assert res.json()["data"]["created"] == 2 and Part.objects.filter(organization=agency_a.org).count() == 2


def test_bad_files(auth_client, agency_a):
    client = auth_client(agency_a.admin)
    assert upload(client, "parts", "x.docx", "hello", True).status_code == 400
    assert upload(client, "parts", "p.csv", "Brand\nBosch\n", True).status_code == 400  # missing required columns
    assert client.get("/api/v1/imports/parts/template/").status_code == 200
    assert client.get("/api/v1/imports/parts/template/?file_format=csv").content.decode("utf-8-sig").startswith("Name,SKU")


def test_super_admin_adds_part_for_an_agency(auth_client, super_admin, agency_a):
    client = auth_client(super_admin)
    assert client.post("/api/v1/inventory/parts/", {"name": "Fork oil", "sku": "FO-1"}, format="json").status_code == 400
    res = client.post("/api/v1/inventory/parts/", {"name": "Fork oil", "sku": "FO-1", "organization": str(agency_a.org.id)},
                      format="json")
    assert res.status_code == 201, res.json()
    assert res.json()["data"]["organization_name"] == agency_a.org.name
    part_id = res.json()["data"]["id"]
    assert client.patch(f"/api/v1/inventory/parts/{part_id}/", {"brand": "Motul"}, format="json").status_code == 200
