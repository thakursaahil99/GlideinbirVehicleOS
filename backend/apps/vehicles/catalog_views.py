"""Showroom catalogue API: vehicle models with stock, and who each unit was sold to."""
import django_filters
from django.db import IntegrityError
from django.db.models import F
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.core.mixins import TenantScopedViewSetMixin
from apps.core.permissions import IsAgencyManager, IsAgencyUser, IsSuperAdmin
from apps.core.tenancy import get_user_organization

from .catalog_services import VehicleCatalogService
from .models import VehicleModel, VehicleSale
from .serializers import StockAdjustSerializer, VehicleModelSerializer, VehicleSaleSerializer


class _CatalogPermissions:
    """Any agency member (and Super Admin) reads; agency admins and managers write."""

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [(IsSuperAdmin | IsAgencyUser)()]
        return [IsAgencyManager()]


class VehicleModelFilter(django_filters.FilterSet):
    low_stock = django_filters.BooleanFilter(method="filter_low_stock")

    class Meta:
        model = VehicleModel
        fields = ("vehicle_type", "brand", "is_active", "fuel_type")

    def filter_low_stock(self, qs, name, value):
        return qs.filter(stock_quantity__lte=F("minimum_stock")) if value else qs


_tag = extend_schema(tags=["showroom"])


@extend_schema_view(list=_tag, retrieve=_tag, create=_tag, partial_update=_tag)
class VehicleModelViewSet(_CatalogPermissions, TenantScopedViewSetMixin, mixins.ListModelMixin,
                          mixins.RetrieveModelMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin,
                          viewsets.GenericViewSet):
    queryset = VehicleModel.objects.all()
    serializer_class = VehicleModelSerializer
    filterset_class = VehicleModelFilter
    search_fields = ("brand", "name", "variant", "colours")
    ordering_fields = ("brand", "name", "stock_quantity", "launch_year", "ex_showroom_price", "created_at")
    http_method_names = ["get", "post", "patch", "head", "options"]

    def _save(self, serializer, **kwargs):
        try:
            serializer.save(**kwargs)
        except IntegrityError as exc:
            raise ValidationError({"name": ["This brand, model and variant already exists."]}) from exc

    def perform_create(self, serializer):
        self._save(serializer, organization=self.get_tenant())

    def perform_update(self, serializer):
        self._save(serializer)

    @extend_schema(tags=["showroom"], summary="Add (+) or remove (−) units from stock",
                   request=StockAdjustSerializer, responses={200: VehicleModelSerializer})
    @action(detail=True, methods=["post"])
    def stock(self, request, pk=None):
        serializer = StockAdjustSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vm = VehicleCatalogService.adjust_stock(vehicle_model=self.get_object(), actor=request.user,
                                                request=request, **serializer.validated_data)
        return Response(VehicleModelSerializer(vm).data)


@extend_schema_view(list=_tag, retrieve=_tag, create=_tag, partial_update=_tag,
                    destroy=extend_schema(tags=["showroom"], summary="Cancel a sale (unit returns to stock)"))
class VehicleSaleViewSet(_CatalogPermissions, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = VehicleSale.objects.select_related("vehicle_model", "sold_by")
    serializer_class = VehicleSaleSerializer
    filterset_fields = ("vehicle_model", "customer", "sold_on")
    search_fields = ("buyer_name", "buyer_phone", "chassis_number", "registration_number", "invoice_number",
                     "vehicle_model__brand", "vehicle_model__name")
    ordering_fields = ("sold_on", "sale_price", "created_at")
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        org = get_user_organization(self.request.user)
        ctx["organization_id"] = org.pk if org else None
        return ctx

    def perform_create(self, serializer):
        serializer.instance = VehicleCatalogService.record_sale(
            organization=self.get_tenant(), data=serializer.validated_data, actor=self.request.user,
            request=self.request)

    def perform_update(self, serializer):
        new_model = serializer.validated_data.get("vehicle_model")
        if new_model is not None and new_model.pk != serializer.instance.vehicle_model_id:
            raise ValidationError({"vehicle_model": ["Cancel the sale and record a new one to change the model."]})
        serializer.save()

    def perform_destroy(self, instance):
        VehicleCatalogService.cancel_sale(sale=instance, actor=self.request.user, request=self.request)
