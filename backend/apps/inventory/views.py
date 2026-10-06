import django_filters
from django.db import transaction
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Max, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.exceptions import BusinessRuleViolation
from apps.core.mixins import TenantScopedViewSetMixin
from apps.core.permissions import IsAgencyManager, IsAgencyUser, IsSuperAdmin
from apps.core.tenancy import get_user_organization
from apps.organizations.models import Organization
from apps.vehicles.models import Vehicle, VehicleType

from .models import Part, PartCategory, PartFitment, StockTransaction, Supplier, TransactionType
from .services import InventoryService, fits_vehicle_q, inventory_summary, stock_status


class TenantChoiceField(serializers.PrimaryKeyRelatedField):
    """FK picker limited to the caller's own agency, so a part can't point at another tenant's row."""

    def get_queryset(self):
        org = self.context.get("organization")
        return super().get_queryset().filter(organization=org) if org else super().get_queryset().none()


class PartFitmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = PartFitment
        fields = ("id", "vehicle_type", "brand", "model", "year_from", "year_to")
        read_only_fields = ("id",)

    def validate(self, attrs):
        attrs["brand"] = attrs["brand"].strip()
        attrs["model"] = attrs.get("model", "").strip()
        if not attrs["brand"]:
            raise serializers.ValidationError({"brand": "Brand is required."})
        lo, hi = attrs.get("year_from"), attrs.get("year_to")
        if lo and hi and lo > hi:
            raise serializers.ValidationError({"year_to": "Must be the same as or after the start year."})
        return attrs


class PartSerializer(serializers.ModelSerializer):
    is_low_stock = serializers.BooleanField(read_only=True)
    stock_status = serializers.SerializerMethodField()
    category = TenantChoiceField(queryset=PartCategory.objects.all(), allow_null=True, required=False)
    category_name = serializers.CharField(source="category.name", read_only=True, default=None)
    preferred_supplier = TenantChoiceField(queryset=Supplier.objects.all(), allow_null=True, required=False)
    preferred_supplier_name = serializers.CharField(source="preferred_supplier.name", read_only=True, default=None)
    fitments = PartFitmentSerializer(many=True, required=False)
    organization_name = serializers.CharField(source="organization.name", read_only=True)

    class Meta:
        model = Part
        fields = ("id", "organization", "organization_name", "name", "sku", "brand", "category", "category_name", "preferred_supplier",
                  "preferred_supplier_name", "hsn_code", "rack_location", "description", "universal", "fitments",
                  "purchase_price", "selling_price", "tax_rate", "stock_quantity", "minimum_stock", "unit", "active",
                  "is_low_stock", "stock_status", "created_at", "updated_at")
        # Stock only changes through transactions, never by editing the number.
        read_only_fields = ("id", "organization", "stock_quantity", "is_low_stock", "created_at", "updated_at")

    def get_stock_status(self, obj) -> str:
        return stock_status(obj)

    def validate_sku(self, value):
        value = value.strip().upper()
        org = self.context["organization"]
        qs = Part.objects.filter(organization=org, sku=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A part with this SKU already exists.")
        return value

    @transaction.atomic
    def create(self, validated_data):
        fitments = validated_data.pop("fitments", [])
        part = super().create(validated_data)
        self._save_fitments(part, fitments)
        return part

    @transaction.atomic
    def update(self, instance, validated_data):
        fitments = validated_data.pop("fitments", None)
        part = super().update(instance, validated_data)
        if fitments is not None:  # omitted = keep; [] = clear
            part.fitments.all().delete()
            self._save_fitments(part, fitments)
        return part

    @staticmethod
    def _save_fitments(part, fitments):
        PartFitment.objects.bulk_create(
            PartFitment(organization=part.organization, part=part, **row) for row in fitments)


class PartCategorySerializer(serializers.ModelSerializer):
    parts_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = PartCategory
        fields = ("id", "name", "description", "parts_count")

    def validate_name(self, value):
        value = value.strip()
        qs = PartCategory.objects.filter(organization=self.context["organization"], name__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("This category already exists.")
        return value


class SupplierSerializer(serializers.ModelSerializer):
    parts_count = serializers.IntegerField(read_only=True, default=0)
    purchase_count = serializers.IntegerField(read_only=True, default=0)
    purchase_total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True, default=0)
    last_purchase_at = serializers.DateTimeField(read_only=True, default=None)

    class Meta:
        model = Supplier
        fields = ("id", "name", "contact_person", "phone", "email", "gst_number", "address", "notes", "active",
                  "parts_count", "purchase_count", "purchase_total", "last_purchase_at", "created_at")
        read_only_fields = ("id", "created_at")

    def validate_name(self, value):
        value = value.strip()
        qs = Supplier.objects.filter(organization=self.context["organization"], name__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A supplier with this name already exists.")
        return value

    def to_internal_value(self, data):
        # Normalise before the model's GSTIN regex runs, so lowercase input is accepted.
        if isinstance(data.get("gst_number"), str):
            data = {**data, "gst_number": data["gst_number"].strip().upper()}
        return super().to_internal_value(data)


class StockTransactionSerializer(serializers.ModelSerializer):
    part_name = serializers.CharField(source="part.name", read_only=True)
    job_card_number = serializers.CharField(source="job_card.job_card_number", read_only=True, default=None)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True, default=None)
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True, default=None)

    class Meta:
        model = StockTransaction
        fields = ("id", "part", "part_name", "transaction_type", "quantity", "unit_price", "balance_after",
                  "job_card", "job_card_number", "supplier", "supplier_name", "reference", "note", "created_by_name",
                  "created_at")
        read_only_fields = fields


class StockMoveSerializer(serializers.Serializer):
    transaction_type = serializers.ChoiceField(choices=[TransactionType.PURCHASE, TransactionType.SALE,
                                                        TransactionType.ADJUSTMENT, TransactionType.RETURN])
    quantity = serializers.DecimalField(max_digits=12, decimal_places=2,
                                        help_text="Positive; ADJUSTMENT may be negative")
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, min_value=0)
    supplier = serializers.UUIDField(required=False, allow_null=True, help_text="Purchases only")
    reference = serializers.CharField(required=False, allow_blank=True, max_length=100, default="")
    note = serializers.CharField(required=False, allow_blank=True, max_length=300, default="")


class PartFilter(django_filters.FilterSet):
    low_stock = django_filters.BooleanFilter(method="filter_low")
    stock_status = django_filters.ChoiceFilter(
        method="filter_status", choices=[(s, s) for s in ("IN_STOCK", "LOW_STOCK", "OUT_OF_STOCK")])
    category = django_filters.UUIDFilter(field_name="category_id")
    supplier = django_filters.UUIDFilter(field_name="preferred_supplier_id")
    uncategorised = django_filters.BooleanFilter(field_name="category", lookup_expr="isnull")

    class Meta:
        model = Part
        fields = ("active", "unit", "brand", "universal")

    def filter_low(self, qs, name, value):
        if value is None:
            return qs
        return qs.filter(stock_quantity__lte=F("minimum_stock")) if value else qs.filter(
            stock_quantity__gt=F("minimum_stock"))

    def filter_status(self, qs, name, value):
        return {
            "OUT_OF_STOCK": qs.filter(stock_quantity__lte=0),
            "LOW_STOCK": qs.filter(stock_quantity__gt=0, stock_quantity__lte=F("minimum_stock")),
            "IN_STOCK": qs.filter(stock_quantity__gt=0).filter(stock_quantity__gt=F("minimum_stock")),
        }[value]


class TenantContextMixin:
    """
    Agency users always work in their own agency. A Super Admin picks the agency with
    `organization` in the body when creating; edits use the record's own agency.
    """

    def _super_admin_org(self):
        if self.kwargs.get("pk"):
            obj = self.get_queryset().filter(pk=self.kwargs["pk"]).select_related("organization").first()
            return obj.organization if obj else None
        org_id = self.request.data.get("organization") if hasattr(self.request, "data") else None
        return Organization.objects.filter(pk=org_id).first() if org_id else None

    def get_tenant(self):
        if self.request.user.is_super_admin:
            org = self._super_admin_org()
            if org is None:
                raise serializers.ValidationError({"organization": "Choose the agency."})
            return org
        return super().get_tenant()

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        user = self.request.user
        ctx["organization"] = (self._super_admin_org() if user.is_authenticated and user.is_super_admin
                               else get_user_organization(user))
        return ctx


@extend_schema_view(
    list=extend_schema(tags=["inventory"], summary="Parts (filter low_stock=true for re-order list)"),
    retrieve=extend_schema(tags=["inventory"]), create=extend_schema(tags=["inventory"]),
    partial_update=extend_schema(tags=["inventory"]),
)
class PartViewSet(TenantContextMixin, TenantScopedViewSetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                  mixins.CreateModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    queryset = Part.objects.select_related("organization", "category", "preferred_supplier").prefetch_related("fitments")
    serializer_class = PartSerializer
    filterset_class = PartFilter
    search_fields = ("name", "sku", "brand", "hsn_code", "rack_location")
    ordering_fields = ("name", "stock_quantity", "selling_price")
    ordering = ("name",)
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_permissions(self):
        if self.action in ("list", "retrieve", "transactions", "summary", "compatible", "fitment_options"):
            return [(IsSuperAdmin | IsAgencyUser)()]
        return [(IsAgencyManager | IsSuperAdmin)()]

    @extend_schema(tags=["inventory"], summary="Purchase, sale, adjustment or return for a part",
                   request=StockMoveSerializer, responses={201: StockTransactionSerializer})
    @action(detail=True, methods=["post"])
    def move(self, request, pk=None):
        serializer = StockMoveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        part = self.get_object()
        supplier_id = data.pop("supplier", None)
        supplier = None
        if supplier_id:
            supplier = Supplier.objects.filter(organization=part.organization, pk=supplier_id).first()
            if supplier is None:
                raise BusinessRuleViolation("Unknown supplier.", code="INVALID_SUPPLIER")
        tx = InventoryService.move(part=part, actor=request.user, request=request, supplier=supplier, **data)
        return Response(StockTransactionSerializer(tx).data, status=status.HTTP_201_CREATED)

    @extend_schema(tags=["inventory"], summary="Stock ledger for a part",
                   responses={200: StockTransactionSerializer(many=True)})
    @action(detail=True, methods=["get"])
    def transactions(self, request, pk=None):
        qs = StockTransaction.objects.filter(part=self.get_object()).select_related(
            "part", "job_card", "supplier", "created_by").order_by("-line_no")
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(StockTransactionSerializer(page, many=True).data)

    @extend_schema(tags=["inventory"], summary="Stock value, re-order counts, value by category and dead stock")
    @action(detail=False, methods=["get"])
    def summary(self, request):
        return Response(inventory_summary(self.filter_queryset(self.get_queryset())))

    @extend_schema(
        tags=["inventory"], summary="Parts that fit a vehicle (by vehicle id, or type/brand/model/year)",
        parameters=[OpenApiParameter("vehicle", str), OpenApiParameter("vehicle_type", str),
                    OpenApiParameter("brand", str), OpenApiParameter("model", str), OpenApiParameter("year", int)],
        responses={200: PartSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def compatible(self, request):
        params = request.query_params
        vehicle_id = params.get("vehicle")
        if vehicle_id:
            vehicle = Vehicle.objects.for_user(request.user).filter(pk=vehicle_id).first()
            if vehicle is None:
                raise BusinessRuleViolation("Vehicle not found.", code="NOT_FOUND")
            criteria = {"brand": vehicle.brand, "model": vehicle.model, "vehicle_type": vehicle.vehicle_type,
                        "year": vehicle.manufacturing_year}
        else:
            year = params.get("year")
            criteria = {"brand": params.get("brand", ""), "model": params.get("model", ""),
                        "vehicle_type": params.get("vehicle_type", ""),
                        "year": int(year) if year and year.isdigit() else None}
        if not criteria["brand"].strip():
            raise BusinessRuleViolation("Choose a vehicle brand.", code="BRAND_REQUIRED")
        if criteria["vehicle_type"] and criteria["vehicle_type"] not in VehicleType.values:
            raise BusinessRuleViolation("Unknown vehicle type.", code="INVALID_VEHICLE_TYPE")
        # Filter in a subquery so a part with several matching fitments appears once. The generic list
        # filters are skipped on purpose: ?brand= here is the vehicle's brand, not the part's.
        matching = Part.objects.filter(fits_vehicle_q(**criteria)).values("pk")
        qs = self.get_queryset().filter(pk__in=matching, active=True).order_by("name")
        if params.get("stock_status") in ("IN_STOCK", "LOW_STOCK", "OUT_OF_STOCK"):
            qs = PartFilter().filter_status(qs, "stock_status", params["stock_status"])
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    @extend_schema(tags=["inventory"], summary="Brands and models that parts are tagged for (picker options)")
    @action(detail=False, methods=["get"], url_path="fitment-options")
    def fitment_options(self, request):
        rows = (PartFitment.objects.for_user(request.user).values("vehicle_type", "brand", "model")
                .annotate(parts=Count("part", distinct=True)).order_by("brand", "model"))
        return Response(list(rows))


class _ManagedTenantViewSet(TenantContextMixin, TenantScopedViewSetMixin, mixins.ListModelMixin,
                            mixins.RetrieveModelMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin,
                            mixins.DestroyModelMixin, viewsets.GenericViewSet):
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [(IsSuperAdmin | IsAgencyUser)()]
        return [(IsAgencyManager | IsSuperAdmin)()]


@extend_schema_view(list=extend_schema(tags=["inventory"], summary="Part categories"),
                    retrieve=extend_schema(tags=["inventory"]), create=extend_schema(tags=["inventory"]),
                    partial_update=extend_schema(tags=["inventory"]), destroy=extend_schema(tags=["inventory"]))
class PartCategoryViewSet(_ManagedTenantViewSet):
    """Deleting a category leaves its parts uncategorised."""

    queryset = PartCategory.objects.annotate(parts_count=Count("parts"))
    serializer_class = PartCategorySerializer
    search_fields = ("name",)
    ordering = ("name",)
    pagination_class = None


@extend_schema_view(list=extend_schema(tags=["inventory"], summary="Suppliers with purchase totals"),
                    retrieve=extend_schema(tags=["inventory"]), create=extend_schema(tags=["inventory"]),
                    partial_update=extend_schema(tags=["inventory"]), destroy=extend_schema(tags=["inventory"]))
class SupplierViewSet(_ManagedTenantViewSet):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    filterset_fields = ("active",)
    search_fields = ("name", "contact_person", "phone", "gst_number")
    ordering_fields = ("name", "purchase_total", "last_purchase_at")
    ordering = ("name",)

    def get_queryset(self):
        purchase = Q(stock_transactions__transaction_type=TransactionType.PURCHASE)
        value = ExpressionWrapper(F("stock_transactions__quantity") * F("stock_transactions__unit_price"),
                                  output_field=DecimalField(max_digits=14, decimal_places=2))
        # Parts are counted in a subquery so the purchases join can't inflate the number.
        parts = (Part.objects.filter(preferred_supplier=OuterRef("pk")).values("preferred_supplier")
                 .annotate(n=Count("id")).values("n")[:1])
        return super().get_queryset().annotate(
            parts_count=Coalesce(Subquery(parts), 0),
            purchase_count=Count("stock_transactions", filter=purchase, distinct=True),
            purchase_total=Coalesce(Sum(value, filter=purchase), 0, output_field=value.output_field),
            last_purchase_at=Max("stock_transactions__created_at", filter=purchase),
        )

    def destroy(self, request, *args, **kwargs):
        supplier = self.get_object()
        if supplier.stock_transactions.exists():
            raise BusinessRuleViolation("This supplier has purchase history. Mark it inactive instead.",
                                        code="SUPPLIER_IN_USE")
        return super().destroy(request, *args, **kwargs)
