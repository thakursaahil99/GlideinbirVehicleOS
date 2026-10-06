"""
Bulk import from CSV, Excel (.xlsx) or PDF (a table) for agency data.

Every row goes through the same validation as the matching "Add" form. A dry run
executes the whole import inside a transaction and rolls it back, so the preview
reports exactly what a real import would do.
"""

import csv
import io
import re
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.constants import Role, StaffPermission
from apps.core.exceptions import BusinessRuleViolation
from apps.core.tenancy import get_user_membership

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_ROWS = 2000


# ---------------------------------------------------------------- parsing

def _norm(text):
    return re.sub(r"[^a-z0-9]+", "_", str(text or "").strip().lower()).strip("_")


def _cell(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def read_table(upload):
    """Return (headers, rows as lists of strings) from a CSV, XLSX or PDF upload."""
    name = (upload.name or "").lower()
    if upload.size > MAX_FILE_BYTES:
        raise ValidationError({"file": "File is larger than 5 MB."})
    raw = upload.read()
    if name.endswith(".csv") or name.endswith(".txt"):
        text = raw.decode("utf-8-sig", errors="replace")
        try:
            dialect = csv.Sniffer().sniff(text[:2048], delimiters=",;\t")
        except csv.Error:  # single column or ambiguous: plain comma CSV
            dialect = csv.excel
        table = [row for row in csv.reader(io.StringIO(text), dialect) if any(c.strip() for c in row)]
    elif name.endswith(".xlsx") or name.endswith(".xlsm"):
        from openpyxl import load_workbook

        try:
            sheet = load_workbook(io.BytesIO(raw), read_only=True, data_only=True).worksheets[0]
        except Exception as exc:  # corrupt or not really xlsx
            raise ValidationError({"file": "Could not read this Excel file."}) from exc
        table = [[_cell(c) for c in row] for row in sheet.iter_rows(values_only=True)]
        table = [row for row in table if any(row)]
    elif name.endswith(".pdf"):
        import pdfplumber

        table = []
        try:
            with pdfplumber.open(io.BytesIO(raw)) as pdf:
                for page in pdf.pages:
                    for t in page.extract_tables():
                        for row in t:
                            cells = [_cell(c).replace("\n", " ") for c in row]
                            if not any(cells):
                                continue
                            # Tables split across pages repeat the header; keep only the first.
                            if table and [_norm(c) for c in cells] == [_norm(c) for c in table[0]]:
                                continue
                            table.append(cells)
        except Exception as exc:
            raise ValidationError({"file": "Could not read this PDF."}) from exc
        if not table:
            raise ValidationError({"file": "No table found in the PDF. Use a PDF that contains a table with a header row."})
    else:
        raise ValidationError({"file": "Upload a .csv, .xlsx or .pdf file."})
    if not table:
        raise ValidationError({"file": "The file is empty."})
    headers, rows = table[0], table[1:]
    if len(rows) > MAX_ROWS:
        raise ValidationError({"file": f"Too many rows ({len(rows)}). Import at most {MAX_ROWS} at a time."})
    return headers, rows


def _decimal(value, field):
    cleaned = re.sub(r"[₹,\s]|rs\.?|inr", "", value, flags=re.I)
    try:
        return str(Decimal(cleaned))
    except InvalidOperation as exc:
        raise BusinessRuleViolation(f"{field}: “{value}” is not a number.") from exc


def _bool(value):
    return value.strip().lower() in ("1", "yes", "y", "true", "haan", "ha")


# ---------------------------------------------------------------- resources

class Resource:
    key = ""
    label = ""
    columns = []  # (field, label, required, example, aliases)
    staff_permission = None  # code a manager/staff needs; admins always pass

    def column_map(self, headers):
        lookup = {}
        for field, label, _req, _ex, aliases in self.columns:
            for name in (field, label, *aliases):
                lookup[_norm(name)] = field
        mapping, unknown = {}, []
        for i, h in enumerate(headers):
            field = lookup.get(_norm(h))
            if field and field not in mapping.values():
                mapping[i] = field
            elif _norm(h):
                unknown.append(h)
        missing = [label for field, label, req, _ex, _al in self.columns if req and field not in mapping.values()]
        return mapping, unknown, missing

    def import_row(self, data, *, organization, actor, request):  # returns "created" | "updated" | "skipped"
        raise NotImplementedError


class PartsResource(Resource):
    key, label = "parts", "Spare parts"
    columns = [
        ("name", "Name", True, "Brake shoe set", ("part", "part_name", "item", "description_name")),
        ("sku", "SKU", True, "BRK-SHOE-ACT", ("part_no", "part_number", "code", "item_code")),
        ("brand", "Brand", False, "Bosch", ("make", "company")),
        ("category", "Category", False, "Brakes", ("group",)),
        ("supplier", "Supplier", False, "Sharma Auto Parts", ("dealer", "vendor")),
        ("hsn_code", "HSN code", False, "8714", ("hsn",)),
        ("rack_location", "Rack / shelf", False, "Rack B · Shelf 1", ("rack", "location", "shelf")),
        ("unit", "Unit", False, "PCS", ("uom",)),
        ("purchase_price", "Purchase price", False, "180", ("cost", "buy_price", "purchase_rate", "mrp_cost")),
        ("selling_price", "Selling price", False, "320", ("price", "sale_price", "mrp", "rate")),
        ("tax_rate", "GST %", False, "18", ("gst", "tax", "gst_rate")),
        ("minimum_stock", "Re-order level", False, "3", ("min_stock", "reorder_level", "minimum")),
        ("opening_stock", "Opening stock", False, "10", ("stock", "qty", "quantity", "current_stock")),
        ("fits", "Fits vehicles", False, "SCOOTER: Honda / Activa 6G / 2020-2024; Honda / Dio", ("fitment", "compatible", "vehicles")),
        ("universal", "Universal", False, "no", ("fits_all",)),
    ]

    @staticmethod
    def parse_fits(text):
        """`[TYPE:] Brand / Model / 2018-2022` entries separated by ; or |."""
        from apps.vehicles.models import VehicleType

        fitments = []
        for entry in re.split(r"[;|\n]", text):
            entry = entry.strip()
            if not entry:
                continue
            vtype = ""
            m = re.match(r"^([A-Za-z ]+):\s*(.*)$", entry)
            if m and m.group(1).strip().upper().replace(" ", "") in VehicleType.values + ["SCOOTY"]:
                vtype = m.group(1).strip().upper().replace("SCOOTY", "SCOOTER")
                entry = m.group(2)
            parts = [p.strip() for p in entry.split("/")]
            row = {"vehicle_type": vtype, "brand": parts[0], "model": parts[1] if len(parts) > 1 else "",
                   "year_from": None, "year_to": None}
            if len(parts) > 2 and parts[2]:
                years = re.findall(r"\d{4}", parts[2])
                row["year_from"] = int(years[0]) if years else None
                row["year_to"] = int(years[1]) if len(years) > 1 else (None if "-" in parts[2] else row["year_from"])
            fitments.append(row)
        return fitments

    def import_row(self, data, *, organization, actor, request):
        from apps.inventory.models import Part, PartCategory, Supplier
        from apps.inventory.services import InventoryService
        from apps.inventory.views import PartSerializer

        payload = {k: v for k, v in data.items() if k in ("name", "sku", "brand", "hsn_code", "rack_location")}
        for f in ("purchase_price", "selling_price", "tax_rate", "minimum_stock"):
            if data.get(f):
                payload[f] = _decimal(data[f], f)
        if data.get("unit"):
            payload["unit"] = data["unit"].upper().rstrip("S") if data["unit"].upper() != "PCS" else "PCS"
        if data.get("category"):
            payload["category"] = PartCategory.objects.get_or_create(organization=organization,
                                                                     name=data["category"].strip())[0].pk
        if data.get("supplier"):
            payload["preferred_supplier"] = Supplier.objects.get_or_create(organization=organization,
                                                                           name=data["supplier"].strip())[0].pk
        if data.get("universal"):
            payload["universal"] = _bool(data["universal"])
        if data.get("fits"):
            payload["fitments"] = self.parse_fits(data["fits"])

        existing = Part.objects.filter(organization=organization, sku=data["sku"].strip().upper()).first()
        serializer = PartSerializer(existing, data=payload, partial=bool(existing),
                                    context={"organization": organization, "request": request})
        if not serializer.is_valid():
            raise BusinessRuleViolation(_flatten(serializer.errors))
        part = serializer.save(**({} if existing else {"organization": organization}))
        if not existing and data.get("opening_stock"):
            qty = Decimal(_decimal(data["opening_stock"], "opening_stock"))
            if qty > 0:
                InventoryService.move(part=part, transaction_type="PURCHASE", quantity=qty, actor=actor,
                                      supplier=part.preferred_supplier, reference="Opening stock (import)",
                                      request=request)
        return "updated" if existing else "created"


class SuppliersResource(Resource):
    key, label = "suppliers", "Suppliers"
    columns = [
        ("name", "Name", True, "Sharma Auto Parts", ("supplier", "dealer", "company")),
        ("contact_person", "Contact person", False, "Rakesh Sharma", ("contact",)),
        ("phone", "Phone", False, "+919812345670", ("mobile", "phone_number")),
        ("email", "E-mail", False, "sales@sharma.example", ("email_address",)),
        ("gst_number", "GSTIN", False, "27AAPFU0939F1ZV", ("gst", "gst_no")),
        ("address", "Address", False, "Lamington Road, Mumbai", ()),
        ("notes", "Notes", False, "", ()),
    ]

    def import_row(self, data, *, organization, actor, request):
        from apps.inventory.models import Supplier
        from apps.inventory.views import SupplierSerializer

        existing = Supplier.objects.filter(organization=organization, name__iexact=data["name"].strip()).first()
        serializer = SupplierSerializer(existing, data=data, partial=bool(existing),
                                        context={"organization": organization})
        if not serializer.is_valid():
            raise BusinessRuleViolation(_flatten(serializer.errors))
        serializer.save(**({} if existing else {"organization": organization}))
        return "updated" if existing else "created"


class CategoriesResource(Resource):
    key, label = "categories", "Part categories"
    columns = [("name", "Name", True, "Brakes", ("category",)), ("description", "Description", False, "", ())]

    def import_row(self, data, *, organization, actor, request):
        from apps.inventory.models import PartCategory

        _obj, created = PartCategory.objects.get_or_create(
            organization=organization, name=data["name"].strip(),
            defaults={"description": data.get("description", "")[:200]})
        return "created" if created else "skipped"


class CustomersResource(Resource):
    key, label = "customers", "Customers"
    staff_permission = StaffPermission.CUSTOMER_CREATE
    columns = [
        ("full_name", "Full name", True, "Aarav Shah", ("name", "customer", "customer_name")),
        ("phone", "Phone", True, "+919800000001", ("mobile", "phone_number", "contact")),
        ("email", "E-mail", False, "aarav@example.com", ("email_address",)),
        ("address", "Address", False, "12 MG Road", ()),
        ("city", "City", False, "Pune", ()),
        ("state", "State", False, "Maharashtra", ()),
        ("pincode", "Pincode", False, "411001", ("pin", "zip")),
        ("notes", "Notes", False, "", ()),
    ]

    def import_row(self, data, *, organization, actor, request):
        from apps.customers.models import Customer
        from apps.customers.serializers import CustomerCreateSerializer
        from apps.customers.services import CustomerService

        data = {**data, "phone": re.sub(r"[\s\-()]", "", data.get("phone", ""))}
        if Customer.objects.filter(agency_links__organization=organization, phone=data["phone"]).exists():
            return "skipped"  # already a customer of this agency
        serializer = CustomerCreateSerializer(data=data)
        if not serializer.is_valid():
            raise BusinessRuleViolation(_flatten(serializer.errors))
        CustomerService.create_walk_in(organization=organization, actor=actor, data=serializer.validated_data,
                                       request=request)
        return "created"


class VehiclesResource(Resource):
    key, label = "vehicles", "Vehicles"
    staff_permission = StaffPermission.VEHICLE_CREATE
    columns = [
        ("customer_phone", "Customer phone", True, "+919800000001", ("phone", "owner_phone", "mobile")),
        ("registration_number", "Registration no.", True, "MH12AB1234", ("reg_no", "registration", "number_plate")),
        ("vehicle_type", "Type", True, "SCOOTER", ("vehicle_type", "category")),
        ("brand", "Brand", True, "Honda", ("make",)),
        ("model", "Model", True, "Activa 6G", ()),
        ("variant", "Variant", False, "DLX", ()),
        ("fuel_type", "Fuel", False, "PETROL", ("fuel_type",)),
        ("manufacturing_year", "Year", False, "2022", ("year", "mfg_year")),
        ("color", "Colour", False, "Red", ("color",)),
        ("odometer", "Odometer (km)", False, "12000", ("km", "odometer")),
        ("vin", "VIN", False, "", ("chassis",)),
    ]

    def import_row(self, data, *, organization, actor, request):
        from apps.customers.models import Customer
        from apps.vehicles.serializers import VehicleSerializer
        from apps.vehicles.services import VehicleService

        phone = re.sub(r"[\s\-()]", "", data.pop("customer_phone", ""))
        customer = Customer.objects.filter(agency_links__organization=organization, phone=phone).first()
        if customer is None:
            raise BusinessRuleViolation(f"No customer with phone {phone}. Import customers first.")
        for f in ("vehicle_type", "fuel_type"):
            if data.get(f):
                data[f] = data[f].strip().upper().replace("SCOOTY", "SCOOTER")
        data["registration_number"] = re.sub(r"\s", "", data["registration_number"]).upper()
        serializer = VehicleSerializer(data={k: v for k, v in data.items() if v != ""})
        if not serializer.is_valid():
            raise BusinessRuleViolation(_flatten(serializer.errors))
        clean = dict(serializer.validated_data)
        clean.pop("customer_id", None)
        VehicleService.create(actor=actor, customer=customer, data=clean, request=request)
        return "created"


RESOURCES = {r.key: r for r in (PartsResource(), SuppliersResource(), CategoriesResource(), CustomersResource(),
                                VehiclesResource())}


def _flatten(errors):
    if isinstance(errors, dict):
        return "; ".join(f"{k}: {_flatten(v)}" for k, v in errors.items())
    if isinstance(errors, list):
        return ", ".join(_flatten(e) for e in errors)
    return str(errors)


def run_import(resource, upload, *, organization, actor, request, dry_run):
    headers, rows = read_table(upload)
    mapping, unknown, missing = resource.column_map(headers)
    if missing:
        raise ValidationError({"file": f"Missing required column(s): {', '.join(missing)}."})
    result = {"resource": resource.key, "dry_run": dry_run, "total_rows": len(rows), "created": 0, "updated": 0,
              "skipped": 0, "errors": [], "unknown_columns": unknown, "preview": []}
    with transaction.atomic():
        for n, raw in enumerate(rows, start=2):  # row 1 is the header
            data = {field: (raw[i].strip() if i < len(raw) else "") for i, field in mapping.items()}
            if len(result["preview"]) < 10:
                result["preview"].append({"row": n, **data})
            missing_values = [label for field, label, req, _e, _a in resource.columns if req and not data.get(field)]
            if missing_values:
                result["errors"].append({"row": n, "message": f"Missing {', '.join(missing_values)}."})
                continue
            try:
                with transaction.atomic():
                    outcome = resource.import_row(dict(data), organization=organization, actor=actor, request=request)
                result[outcome] += 1
            except BusinessRuleViolation as exc:
                result["errors"].append({"row": n, "message": str(exc.detail if hasattr(exc, "detail") else exc)})
            except Exception as exc:  # noqa: BLE001 - one bad row must not sink the file
                result["errors"].append({"row": n, "message": f"Could not import: {exc}"})
        if dry_run:
            transaction.set_rollback(True)
    return result


# ---------------------------------------------------------------- API

def _resolve(request, key):
    resource = RESOURCES.get(key)
    if resource is None:
        raise NotFound("Unknown import type.")
    user = request.user
    if user.role == Role.SUPER_ADMIN:
        from apps.organizations.models import Organization

        org_id = request.data.get("organization") or request.query_params.get("organization")
        organization = Organization.objects.filter(pk=org_id).first() if org_id else None
        if organization is None:
            raise ValidationError({"organization": "Choose the agency to import into."})
        return resource, organization
    membership = get_user_membership(user)
    if membership is None:
        raise PermissionDenied("An active agency membership is required.")
    allowed = user.role in (Role.AGENCY_ADMIN, Role.AGENCY_MANAGER) if resource.staff_permission is None else (
        user.role == Role.AGENCY_ADMIN or membership.has_permission(resource.staff_permission))
    if not allowed:
        raise PermissionDenied("You do not have permission to import this data.")
    return resource, membership.organization


class ImportTypesView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["imports"], summary="Importable data types and their columns")
    def get(self, request):
        return Response([{"key": r.key, "label": r.label,
                          "columns": [{"field": f, "label": lbl, "required": req, "example": ex}
                                      for f, lbl, req, ex, _a in r.columns]} for r in RESOURCES.values()])


class ImportTemplateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["imports"], summary="Download a CSV or Excel template")
    def get(self, request, resource):
        res = RESOURCES.get(resource)
        if res is None:
            raise NotFound("Unknown import type.")
        headers = [lbl for _f, lbl, _r, _e, _a in res.columns]
        example = [ex for _f, _l, _r, ex, _a in res.columns]
        if request.query_params.get("file_format") == "csv":
            buf = io.StringIO()
            csv.writer(buf).writerows([headers, example])
            response = HttpResponse("﻿" + buf.getvalue(), content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = f'attachment; filename="{res.key}-template.csv"'
            return response
        from openpyxl import Workbook
        from openpyxl.styles import Font

        wb = Workbook()
        ws = wb.active
        ws.title = res.label[:31]
        ws.append(headers)
        ws.append(example)
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for i, h in enumerate(headers, start=1):
            ws.column_dimensions[ws.cell(1, i).column_letter].width = max(14, len(h) + 4)
        out = io.BytesIO()
        wb.save(out)
        response = HttpResponse(out.getvalue(),
                                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = f'attachment; filename="{res.key}-template.xlsx"'
        return response


class ImportUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    dry_run = serializers.BooleanField(default=True)
    organization = serializers.UUIDField(required=False)


class ImportView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(tags=["imports"], summary="Preview (dry_run=true) or run an import from CSV / Excel / PDF",
                   request={"multipart/form-data": ImportUploadSerializer})
    def post(self, request, resource):
        res, organization = _resolve(request, resource)
        payload = ImportUploadSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        result = run_import(res, payload.validated_data["file"], organization=organization, actor=request.user,
                            request=request, dry_run=payload.validated_data["dry_run"])
        return Response(result)
