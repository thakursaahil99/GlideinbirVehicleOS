import django_filters
from django.db.models import F
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.mixins import TenantScopedViewSetMixin
from apps.core.permissions import IsAgencyManager, IsAgencyUser, IsSuperAdmin

from .models import Part, StockTransaction, TransactionType
from .services import InventoryService


class PartSerializer(serializers.ModelSerializer):
    is_low_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = Part
        fields = ("id", "name", "sku", "brand", "purchase_price", "selling_price", "tax_rate", "stock_quantity",
                  "minimum_stock", "unit", "active", "is_low_stock", "created_at", "updated_at")
        # Stock only changes through transactions, never by editing the number.
        read_only_fields = ("id", "stock_quantity", "is_low_stock", "created_at", "updated_at")

    def validate_sku(self, value):
        value = value.strip().upper()
        org = self.context["organization"]
        qs = Part.objects.filter(organization=org, sku=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A part with this SKU already exists.")
        return value


class StockTransactionSerializer(serializers.ModelSerializer):
    part_name = serializers.CharField(source="part.name", read_only=True)
    job_card_number = serializers.CharField(source="job_card.job_card_number", read_only=True, default=None)
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True, default=None)

    class Meta:
        model = StockTransaction
        fields = ("id", "part", "part_name", "transaction_type", "quantity", "unit_price", "balance_after",
                  "job_card", "job_card_number", "reference", "note", "created_by_name", "created_at")
        read_only_fields = fields


class StockMoveSerializer(serializers.Serializer):
    transaction_type = serializers.ChoiceField(choices=[TransactionType.PURCHASE, TransactionType.SALE,
                                                        TransactionType.ADJUSTMENT, TransactionType.RETURN])
    quantity = serializers.DecimalField(max_digits=12, decimal_places=2,
                                        help_text="Positive; ADJUSTMENT may be negative")
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, min_value=0)
    reference = serializers.CharField(required=False, allow_blank=True, max_length=100, default="")
    note = serializers.CharField(required=False, allow_blank=True, max_length=300, default="")


class PartFilter(django_filters.FilterSet):
    low_stock = django_filters.BooleanFilter(method="filter_low")

    class Meta:
        model = Part
        fields = ("active", "unit", "brand")

    def filter_low(self, qs, name, value):
        if value is None:
            return qs
        return qs.filter(stock_quantity__lte=F("minimum_stock")) if value else qs.filter(
            stock_quantity__gt=F("minimum_stock"))


@extend_schema_view(
    list=extend_schema(tags=["inventory"], summary="Parts (filter low_stock=true for re-order list)"),
    retrieve=extend_schema(tags=["inventory"]), create=extend_schema(tags=["inventory"]),
    partial_update=extend_schema(tags=["inventory"]),
)
class PartViewSet(TenantScopedViewSetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                  mixins.CreateModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    queryset = Part.objects.all()
    serializer_class = PartSerializer
    filterset_class = PartFilter
    search_fields = ("name", "sku", "brand")
    ordering_fields = ("name", "stock_quantity", "selling_price")
    ordering = ("name",)
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_permissions(self):
        if self.action in ("list", "retrieve", "transactions"):
            return [(IsSuperAdmin | IsAgencyUser)()]
        return [IsAgencyManager()]

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        from apps.core.tenancy import get_user_organization

        ctx["organization"] = get_user_organization(self.request.user)
        return ctx

    @extend_schema(tags=["inventory"], summary="Purchase, sale, adjustment or return for a part",
                   request=StockMoveSerializer, responses={201: StockTransactionSerializer})
    @action(detail=True, methods=["post"])
    def move(self, request, pk=None):
        serializer = StockMoveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tx = InventoryService.move(part=self.get_object(), actor=request.user, request=request,
                                   **serializer.validated_data)
        return Response(StockTransactionSerializer(tx).data, status=status.HTTP_201_CREATED)

    @extend_schema(tags=["inventory"], summary="Stock ledger for a part",
                   responses={200: StockTransactionSerializer(many=True)})
    @action(detail=True, methods=["get"])
    def transactions(self, request, pk=None):
        qs = StockTransaction.objects.filter(part=self.get_object()).select_related(
            "part", "job_card", "created_by").order_by("-line_no")
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(StockTransactionSerializer(page, many=True).data)
