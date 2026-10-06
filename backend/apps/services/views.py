import django_filters
from django.db import transaction
from django.utils.text import slugify
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.response import Response

from apps.accounts.constants import StaffPermission
from apps.audit_logs.models import AuditAction
from apps.audit_logs.services import AuditService, diff, snapshot
from apps.core.db import json_list_contains
from apps.core.exceptions import BusinessRuleViolation
from apps.core.mixins import TenantScopedViewSetMixin
from apps.core.permissions import HasStaffPermission, IsAgencyUser, IsSuperAdmin
from apps.vendors.models import ServiceResource

from .models import Service, ServiceCategory, VendorService
from .serializers import ServiceSerializer, VendorServiceSerializer, VendorServiceUpdateSerializer
from .services import VendorServiceService

CanManageServices = HasStaffPermission(StaffPermission.SERVICE_MANAGE)


class VehicleTypeFilterMixin(django_filters.FilterSet):
    vehicle_type = django_filters.CharFilter(method="filter_vehicle_type")

    def filter_vehicle_type(self, qs, name, value):
        prefix = getattr(self, "service_prefix", "")
        return qs.filter(json_list_contains(f"{prefix}supported_vehicle_types", value.upper()))


class ServiceFilter(VehicleTypeFilterMixin):
    category = django_filters.MultipleChoiceFilter(choices=ServiceCategory.choices)

    class Meta:
        model = Service
        fields = ("category", "active")


@extend_schema_view(
    list=extend_schema(tags=["services"], summary="Global service catalog"),
    retrieve=extend_schema(tags=["services"]),
    create=extend_schema(tags=["services"], summary="Add a catalog service (Super Admin)"),
    partial_update=extend_schema(tags=["services"], summary="Update a catalog service (Super Admin)"),
)
class ServiceViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                     mixins.UpdateModelMixin, viewsets.GenericViewSet):
    serializer_class = ServiceSerializer
    filterset_class = ServiceFilter
    search_fields = ("name", "description")
    ordering_fields = ("name", "base_price", "default_duration", "category")
    ordering = ("category", "name")
    http_method_names = ["get", "post", "patch", "head", "options"]
    queryset = Service.objects.all()

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return super().get_permissions()
        return [IsSuperAdmin()]

    def get_queryset(self):
        qs = Service.objects.all()
        return qs if self.request.user.is_super_admin else qs.filter(active=True)

    def perform_create(self, serializer):
        slug = serializer.validated_data.get("slug") or slugify(serializer.validated_data["name"])
        if Service.objects.filter(slug=slug).exists():
            raise BusinessRuleViolation("A service with this slug already exists.", code="DUPLICATE_SLUG",
                                        details={"slug": ["Already used."]})
        service = serializer.save(slug=slug)
        AuditService.log(AuditAction.SERVICE_PRICE_CHANGED, instance=service, request=self.request,
                         new_data=snapshot(service, ["name", "base_price", "tax", "default_duration"]))

    @transaction.atomic
    def perform_update(self, serializer):
        before = snapshot(serializer.instance, ["base_price", "tax", "default_duration", "active"])
        service = serializer.save()
        old, new = diff(before, snapshot(service, ["base_price", "tax", "default_duration", "active"]))
        if new:
            AuditService.log(AuditAction.SERVICE_PRICE_CHANGED, instance=service, request=self.request,
                             old_data=old, new_data=new)


class VendorServiceFilter(VehicleTypeFilterMixin):
    service_prefix = "service__"
    category = django_filters.CharFilter(field_name="service__category")

    class Meta:
        model = VendorService
        fields = ("active", "online_booking_enabled", "service")


def _check_resource_type(organization, resource_type):
    if resource_type and not ServiceResource.objects.filter(organization=organization, resource_type=resource_type,
                                                            active=True).exists():
        raise BusinessRuleViolation(
            "Add at least one active resource of this type before requiring it.", code="NO_RESOURCES_OF_TYPE",
            details={"required_resource_type": ["No active resources of this type."]},
        )


@extend_schema_view(
    list=extend_schema(tags=["vendor-services"], summary="Services your agency offers"),
    retrieve=extend_schema(tags=["vendor-services"]),
    create=extend_schema(tags=["vendor-services"], summary="Offer a catalog service with your own price/duration"),
    partial_update=extend_schema(tags=["vendor-services"], summary="Change price, duration, capacity, flags"),
    destroy=extend_schema(tags=["vendor-services"], summary="Remove an offering that was never booked"),
)
class VendorServiceViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = VendorService.objects.select_related("service", "organization")
    filterset_class = VendorServiceFilter
    search_fields = ("service__name",)
    ordering_fields = ("service__name", "custom_price", "created_at")
    ordering = ("service__name",)
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [(IsSuperAdmin | IsAgencyUser)()]
        return [(IsAgencyUser & CanManageServices)()]

    def get_serializer_class(self):
        return VendorServiceUpdateSerializer if self.action == "partial_update" else VendorServiceSerializer

    def create(self, request):
        serializer = VendorServiceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        organization = self.get_tenant()
        _check_resource_type(organization, data.get("required_resource_type"))
        offering = VendorServiceService.create(organization=organization, service=data.pop("service"), data=data,
                                               actor=request.user, request=request)
        return Response(VendorServiceSerializer(offering).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        offering = self.get_object()
        serializer = VendorServiceUpdateSerializer(offering, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        if "required_resource_type" in serializer.validated_data:
            _check_resource_type(offering.organization, serializer.validated_data["required_resource_type"])
        offering = VendorServiceService.update(offering=offering, data=serializer.validated_data, actor=request.user,
                                               request=request)
        return Response(VendorServiceSerializer(offering).data)
