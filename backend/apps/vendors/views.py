import uuid
from datetime import timedelta

import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Exists, OuterRef, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.constants import Role, StaffPermission
from apps.audit_logs.models import AuditAction
from apps.audit_logs.services import AuditService, snapshot
from apps.core.db import json_list_contains
from apps.core.mixins import TenantScopedViewSetMixin
from apps.core.permissions import IsAgencyAdmin, IsAgencyManager, IsAgencyUser, IsSuperAdmin
from apps.core.tenancy import get_user_organization
from apps.organizations.models import Membership, Organization
from apps.services.models import VendorService
from apps.services.serializers import PublicVendorServiceSerializer

from . import serializers as s
from .models import Holiday, ServiceResource, SpecialWorkingDay, WorkingHours
from .services import AgencySettingsService, ScheduleService, StaffService, get_agency_settings

READ_ACTIONS = {"list", "retrieve"}


def _looks_like_uuid(value):
    try:
        uuid.UUID(str(value))
        return True
    except ValueError:
        return False


class AgencyReadAdminWriteMixin:
    """Reads: Super Admin or any agency member. Writes: the agency's admin."""

    def get_permissions(self):
        if self.action in READ_ACTIONS:
            return [(IsSuperAdmin | IsAgencyUser)()]
        return [IsAgencyAdmin()]


# ---------------------------------------------------------------- staff
class StaffFilter(django_filters.FilterSet):
    role = django_filters.MultipleChoiceFilter(field_name="user__role", choices=[
        (Role.AGENCY_ADMIN, "Admin"), (Role.AGENCY_MANAGER, "Manager"), (Role.AGENCY_STAFF, "Staff")])

    class Meta:
        model = Membership
        fields = ("is_active",)


@extend_schema_view(
    list=extend_schema(tags=["agency"], summary="List agency staff"),
    retrieve=extend_schema(tags=["agency"], summary="Retrieve a staff member"),
)
class StaffViewSet(TenantScopedViewSetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                   viewsets.GenericViewSet):
    queryset = Membership.objects.select_related("user", "organization")
    serializer_class = s.StaffSerializer
    filterset_class = StaffFilter
    search_fields = ("user__full_name", "user__email", "user__phone")
    ordering_fields = ("user__full_name", "created_at")
    ordering = ("user__full_name",)

    def get_permissions(self):
        if self.action in READ_ACTIONS or self.action == "permission_codes":
            return [(IsSuperAdmin | IsAgencyManager)()]
        return [IsAgencyAdmin()]

    @extend_schema(tags=["agency"], summary="Add a manager or staff member (sends an invite e-mail)",
                   request=s.StaffCreateSerializer, responses={201: s.StaffSerializer})
    def create(self, request):
        serializer = s.StaffCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        membership = StaffService.add_member(organization=self.get_tenant(), actor=request.user, request=request,
                                             **serializer.validated_data)
        return Response(s.StaffSerializer(membership).data, status=status.HTTP_201_CREATED)

    @extend_schema(tags=["agency"], summary="Update role, permissions or contact details",
                   request=s.StaffUpdateSerializer, responses={200: s.StaffSerializer})
    def partial_update(self, request, pk=None):
        serializer = s.StaffUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        membership = StaffService.update_member(membership=self.get_object(), actor=request.user,
                                                data=serializer.validated_data, request=request)
        return Response(s.StaffSerializer(membership).data)

    @extend_schema(tags=["agency"], summary="Re-activate a staff member", request=None,
                   responses={200: s.StaffSerializer})
    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        membership = StaffService.set_member_active(membership=self.get_object(), actor=request.user, active=True,
                                                    request=request)
        return Response(s.StaffSerializer(membership).data)

    @extend_schema(tags=["agency"], summary="Deactivate a staff member (revokes sessions)", request=None,
                   responses={200: s.StaffSerializer})
    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        membership = StaffService.set_member_active(membership=self.get_object(), actor=request.user,
                                                    active=False, request=request)
        return Response(s.StaffSerializer(membership).data)

    @extend_schema(tags=["agency"], summary="All granular staff permission codes",
                   responses={200: s.PermissionCodeSerializer(many=True)})
    @action(detail=False, methods=["get"], url_path="permission-codes", pagination_class=None)
    def permission_codes(self, request):
        return Response([{"code": c.value, "label": c.label} for c in StaffPermission])


# ---------------------------------------------------------------- schedule
@extend_schema_view(list=extend_schema(tags=["agency"], summary="Weekly working hours"))
class WorkingHoursViewSet(TenantScopedViewSetMixin, AgencyReadAdminWriteMixin, mixins.ListModelMixin,
                          viewsets.GenericViewSet):
    queryset = WorkingHours.objects.all()
    serializer_class = s.WorkingHoursSerializer
    pagination_class = None
    filter_backends = []

    @extend_schema(tags=["agency"], summary="Replace the whole weekly schedule",
                   request=s.WeekScheduleSerializer, responses={200: s.WorkingHoursSerializer(many=True)})
    @action(detail=False, methods=["put"])
    def week(self, request):
        serializer = s.WeekScheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rows = ScheduleService.replace_week(organization=self.get_tenant(), actor=request.user, request=request,
                                            intervals=[dict(i) for i in serializer.validated_data["intervals"]])
        return Response(s.WorkingHoursSerializer(rows, many=True).data)


class HolidayFilter(django_filters.FilterSet):
    upcoming = django_filters.BooleanFilter(method="filter_upcoming")

    class Meta:
        model = Holiday
        fields = ("kind",)

    def filter_upcoming(self, qs, name, value):
        return qs.filter(end_date__gte=timezone.localdate()) if value else qs


@extend_schema_view(
    list=extend_schema(tags=["agency"], summary="Holidays & emergency closures"),
    create=extend_schema(tags=["agency"], summary="Add a holiday / closure"),
    retrieve=extend_schema(tags=["agency"]),
    partial_update=extend_schema(tags=["agency"]),
    destroy=extend_schema(tags=["agency"]),
)
class HolidayViewSet(TenantScopedViewSetMixin, AgencyReadAdminWriteMixin, viewsets.ModelViewSet):
    queryset = Holiday.objects.all()
    serializer_class = s.HolidaySerializer
    filterset_class = HolidayFilter
    ordering = ("start_date",)
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def perform_create(self, serializer):
        org = self.get_tenant()
        obj = serializer.save(organization=org)
        AuditService.log(AuditAction.SCHEDULE_CHANGED, organization=org, instance=obj, request=self.request,
                         new_data=snapshot(obj, ["name", "start_date", "end_date", "kind"]))

    def perform_update(self, serializer):
        before = snapshot(serializer.instance, ["name", "start_date", "end_date", "kind"])
        obj = serializer.save()
        AuditService.log(AuditAction.SCHEDULE_CHANGED, organization=obj.organization, instance=obj,
                         request=self.request, old_data=before,
                         new_data=snapshot(obj, ["name", "start_date", "end_date", "kind"]))

    def perform_destroy(self, instance):
        AuditService.log(AuditAction.SCHEDULE_CHANGED, organization=instance.organization, instance=instance,
                         request=self.request, old_data=snapshot(instance, ["name", "start_date", "end_date"]),
                         new_data={"deleted": True})
        instance.delete()


class SpecialDayFilter(django_filters.FilterSet):
    date_from = django_filters.DateFilter(field_name="date", lookup_expr="gte")
    date_to = django_filters.DateFilter(field_name="date", lookup_expr="lte")

    class Meta:
        model = SpecialWorkingDay
        fields = ("date",)


@extend_schema_view(list=extend_schema(tags=["agency"], summary="Special working dates"))
class SpecialWorkingDayViewSet(TenantScopedViewSetMixin, AgencyReadAdminWriteMixin, mixins.ListModelMixin,
                               viewsets.GenericViewSet):
    queryset = SpecialWorkingDay.objects.all()
    serializer_class = s.SpecialWorkingDaySerializer
    filterset_class = SpecialDayFilter
    ordering = ("date", "opens_at")

    @extend_schema(tags=["agency"], summary="Set (or clear with an empty list) the hours for one date",
                   request=s.SpecialDaySetSerializer, responses={200: s.SpecialWorkingDaySerializer(many=True)})
    @action(detail=False, methods=["put"], url_path="set-day")
    def set_day(self, request):
        serializer = s.SpecialDaySetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rows = ScheduleService.replace_special_day(
            organization=self.get_tenant(), actor=request.user, request=request,
            date=serializer.validated_data["date"],
            intervals=[dict(i) for i in serializer.validated_data["intervals"]],
        )
        return Response(s.SpecialWorkingDaySerializer(rows, many=True).data)


# ---------------------------------------------------------------- resources
class ResourceFilter(django_filters.FilterSet):
    class Meta:
        model = ServiceResource
        fields = ("resource_type", "active")


@extend_schema_view(
    list=extend_schema(tags=["agency"], summary="Bays, technicians and equipment"),
    create=extend_schema(tags=["agency"]),
    retrieve=extend_schema(tags=["agency"]),
    partial_update=extend_schema(tags=["agency"]),
    destroy=extend_schema(tags=["agency"], summary="Delete an unused resource (deactivate instead if in use)"),
)
class ServiceResourceViewSet(TenantScopedViewSetMixin, AgencyReadAdminWriteMixin, viewsets.ModelViewSet):
    queryset = ServiceResource.objects.select_related("staff")
    serializer_class = s.ServiceResourceSerializer
    filterset_class = ResourceFilter
    search_fields = ("name",)
    ordering = ("resource_type", "name")
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["organization"] = get_user_organization(self.request.user)
        return ctx

    def perform_create(self, serializer):
        org = self.get_tenant()
        obj = serializer.save(organization=org)
        AuditService.log(AuditAction.RESOURCE_CHANGED, organization=org, instance=obj, request=self.request,
                         new_data=snapshot(obj, ["name", "resource_type", "active"]))

    def perform_update(self, serializer):
        before = snapshot(serializer.instance, ["name", "resource_type", "active", "staff"])
        obj = serializer.save()
        AuditService.log(AuditAction.RESOURCE_CHANGED, organization=obj.organization, instance=obj,
                         request=self.request, old_data=before,
                         new_data=snapshot(obj, ["name", "resource_type", "active", "staff"]))

    def perform_destroy(self, instance):
        org = instance.organization
        snap = snapshot(instance, ["name", "resource_type"])
        instance.delete()
        AuditService.log(AuditAction.RESOURCE_CHANGED, organization=org, model_name="ServiceResource",
                         object_id=str(instance.pk), request=self.request, old_data=snap,
                         new_data={"deleted": True})


# ---------------------------------------------------------------- settings
class AgencySettingsView(APIView):
    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [IsAgencyUser()]
        return [IsAgencyAdmin()]

    @extend_schema(tags=["agency"], summary="Booking settings", responses={200: s.AgencySettingsSerializer})
    def get(self, request):
        return Response(s.AgencySettingsSerializer(get_agency_settings(get_user_organization(request.user))).data)

    @extend_schema(tags=["agency"], summary="Update booking settings", request=s.AgencySettingsSerializer,
                   responses={200: s.AgencySettingsSerializer})
    def patch(self, request):
        org = get_user_organization(request.user)
        serializer = s.AgencySettingsSerializer(get_agency_settings(org), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        obj = AgencySettingsService.update(organization=org, data=serializer.validated_data, actor=request.user,
                                           request=request)
        return Response(s.AgencySettingsSerializer(obj).data)


# ---------------------------------------------------------------- public directory
class VendorDirectoryFilter(django_filters.FilterSet):
    city = django_filters.CharFilter(lookup_expr="iexact")
    state = django_filters.CharFilter(lookup_expr="iexact")

    class Meta:
        model = Organization
        fields = ("city", "state")


@extend_schema_view(
    list=extend_schema(tags=["vendors"], summary="Directory of active agencies (customers compare vendors here)"),
    retrieve=extend_schema(tags=["vendors"], summary="Public agency profile"),
)
class VendorDirectoryViewSet(viewsets.ReadOnlyModelViewSet):
    """Only ACTIVE agencies, only public fields. Available to every signed-in user."""

    serializer_class = s.VendorPublicSerializer
    filterset_class = VendorDirectoryFilter
    # Ordering is handled in get_queryset (price ordering needs the offer annotation).
    filter_backends = [DjangoFilterBackend, SearchFilter]
    search_fields = ("name", "city", "description")
    queryset = Organization.objects.bookable()

    def get_queryset(self):
        """
        ``?service=<id|slug>`` keeps agencies offering that service (bookable) and
        annotates ``offer_price``/``offer_duration`` for side-by-side comparison;
        ``?vehicle_type=CAR`` keeps agencies with at least one bookable service for it.
        """
        qs = Organization.objects.bookable()
        params = self.request.query_params
        offers = VendorService.objects.bookable().filter(organization=OuterRef("pk"))
        if params.get("vehicle_type"):
            offers = offers.filter(json_list_contains("service__supported_vehicle_types", params["vehicle_type"].upper()))
        service = params.get("service")
        if service:
            key = "service_id" if _looks_like_uuid(service) else "service__slug"
            offers = offers.filter(**{key: service})
            price = Coalesce("custom_price", "service__base_price")
            duration = Coalesce("custom_duration", "service__default_duration")
            qs = qs.annotate(
                offer_id=Subquery(offers.values("id")[:1]),
                offer_price=Subquery(offers.annotate(p=price).values("p")[:1]),
                offer_duration=Subquery(offers.annotate(d=duration).values("d")[:1]),
            ).filter(offer_id__isnull=False)
        elif params.get("vehicle_type"):
            qs = qs.filter(Exists(offers))
        if params.get("ordering") in ("price", "-price") and service:
            return qs.order_by(params["ordering"].replace("price", "offer_price"), "name")
        return qs.order_by("name")

    def get_serializer_class(self):
        if self.request.query_params.get("service") and self.action == "list":
            return s.VendorOfferSerializer
        return s.VendorPublicSerializer

    @extend_schema(tags=["vendors"], summary="Bookable services of an agency, with its prices",
                   responses={200: PublicVendorServiceSerializer(many=True)})
    @action(detail=True, methods=["get"])
    def services(self, request, pk=None):
        org = self.get_object()
        qs = VendorService.objects.bookable().filter(organization=org).select_related("service", "organization")
        if request.query_params.get("vehicle_type"):
            qs = qs.filter(json_list_contains("service__supported_vehicle_types",
                                         request.query_params["vehicle_type"].upper()))
        page = self.paginate_queryset(qs.order_by("service__name"))
        return self.get_paginated_response(PublicVendorServiceSerializer(page, many=True).data)

    @extend_schema(tags=["vendors"], summary="Weekly hours and upcoming closures",
                   parameters=[OpenApiParameter("days", int, description="Look-ahead for closures (default 60)")])
    @action(detail=True, methods=["get"])
    def hours(self, request, pk=None):
        org = self.get_object()
        try:
            days = max(1, min(int(request.query_params.get("days", 60)), 365))
        except ValueError:
            days = 60
        today = timezone.localdate()
        weekly = WorkingHours.objects.filter(organization=org).order_by("weekday", "opens_at")
        closures = Holiday.objects.filter(organization=org, end_date__gte=today,
                                          start_date__lte=today + timedelta(days=days)).order_by("start_date")
        return Response({
            "weekly": [{"weekday": w.weekday, "weekday_display": w.get_weekday_display(),
                        "opens_at": w.opens_at, "closes_at": w.closes_at} for w in weekly],
            "upcoming_closures": s.PublicHolidaySerializer(closures, many=True).data,
        })
