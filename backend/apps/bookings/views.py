from datetime import timedelta

import django_filters
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.accounts.constants import StaffPermission
from apps.core.permissions import HasStaffPermission, IsAgencyUser, IsCustomer, IsSuperAdmin

from . import serializers as s
from .models import Booking, BookingStatus
from .services import BookingService

CanView = HasStaffPermission(StaffPermission.BOOKING_VIEW)


class BookingFilter(django_filters.FilterSet):
    status = django_filters.MultipleChoiceFilter(choices=BookingStatus.choices)
    date_from = django_filters.DateFilter(field_name="booking_date", lookup_expr="gte")
    date_to = django_filters.DateFilter(field_name="booking_date", lookup_expr="lte")
    service = django_filters.UUIDFilter(field_name="vendor_service__service_id")
    organization = django_filters.UUIDFilter(field_name="organization_id")
    upcoming = django_filters.BooleanFilter(method="filter_upcoming")

    class Meta:
        model = Booking
        fields = ("status", "payment_status", "vendor_service", "assigned_staff", "assigned_resource", "customer",
                  "vehicle", "source")

    def filter_upcoming(self, qs, name, value):
        if value is None:
            return qs
        now = timezone.now()
        return qs.filter(start_datetime__gte=now) if value else qs.filter(start_datetime__lt=now)


SELECT = ("organization", "customer", "vehicle", "vendor_service__service", "assigned_staff", "assigned_resource",
          "job_card", "invoice")


@extend_schema_view(
    list=extend_schema(tags=["bookings"], summary="Bookings (customer: own; staff: assigned; managers/admins: agency)"),
    retrieve=extend_schema(tags=["bookings"]),
)
class BookingViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = s.BookingSerializer
    filterset_class = BookingFilter
    search_fields = ("booking_number", "customer__full_name", "customer__phone", "vehicle__registration_number")
    ordering_fields = ("start_datetime", "created_at", "status")
    ordering = ("-start_datetime",)
    queryset = Booking.objects.all()

    def get_permissions(self):
        return [(IsSuperAdmin | IsCustomer | (IsAgencyUser & CanView))()]

    def get_queryset(self):
        return Booking.objects.for_user(self.request.user).select_related(*SELECT)

    def _respond(self, booking, code=status.HTTP_200_OK):
        booking = Booking.objects.select_related(*SELECT).get(pk=booking.pk)
        return Response(s.BookingSerializer(booking, context=self.get_serializer_context()).data, status=code)

    @extend_schema(tags=["bookings"], summary="Create a booking (slot re-validated under a row lock)",
                   request=s.BookingCreateSerializer, responses={201: s.BookingSerializer})
    def create(self, request):
        serializer = s.BookingCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        booking = BookingService.create(
            actor=request.user, vehicle_id=d["vehicle"], vendor_service_id=d["vendor_service"],
            start_datetime=d["start_datetime"], customer_id=d.get("customer"), customer_notes=d["customer_notes"],
            pickup_requested=d["pickup_requested"], drop_requested=d["drop_requested"],
            pickup_address=d["pickup_address"], request=request,
        )
        return self._respond(booking, status.HTTP_201_CREATED)

    @extend_schema(tags=["bookings"], summary="Edit notes (customer notes / internal notes)",
                   request=s.BookingNotesSerializer, responses={200: s.BookingSerializer})
    def partial_update(self, request, pk=None):
        serializer = s.BookingNotesSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        booking = BookingService.update_notes(booking=self.get_object(), actor=request.user,
                                              data=serializer.validated_data, request=request)
        return self._respond(booking)

    def _transition(self, request, action_name):
        serializer = s.NoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        booking = BookingService.transition(booking=self.get_object(), action=action_name, actor=request.user,
                                            note=serializer.validated_data["note"], request=request)
        return self._respond(booking)

    _t = extend_schema(tags=["bookings"], request=s.NoteSerializer, responses={200: s.BookingSerializer})

    @_t
    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        return self._transition(request, "confirm")

    @_t
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self._transition(request, "reject")

    @_t
    @action(detail=True, methods=["post"], url_path="receive-vehicle")
    def receive_vehicle(self, request, pk=None):
        return self._transition(request, "receive_vehicle")

    @_t
    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        return self._transition(request, "start")

    @_t
    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        return self._transition(request, "complete")

    @_t
    @action(detail=True, methods=["post"], url_path="no-show")
    def no_show(self, request, pk=None):
        return self._transition(request, "no_show")

    @extend_schema(tags=["bookings"], summary="Cancel (reason required; bookings are never deleted)",
                   request=s.CancelSerializer, responses={200: s.BookingSerializer})
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        serializer = s.CancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        booking = BookingService.cancel(booking=self.get_object(), actor=request.user,
                                        reason=serializer.validated_data["reason"], request=request)
        return self._respond(booking)

    @extend_schema(tags=["bookings"], summary="Reschedule to another available slot",
                   request=s.RescheduleSerializer, responses={200: s.BookingSerializer})
    @action(detail=True, methods=["post"])
    def reschedule(self, request, pk=None):
        serializer = s.RescheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        booking = BookingService.reschedule(booking=self.get_object(), actor=request.user, request=request,
                                            **serializer.validated_data)
        return self._respond(booking)

    @extend_schema(tags=["bookings"], summary="Assign a staff member and/or resource (conflict-checked)",
                   request=s.AssignSerializer, responses={200: s.BookingSerializer})
    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        serializer = s.AssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        booking = BookingService.assign(booking=self.get_object(), actor=request.user, request=request,
                                        staff_id=serializer.validated_data.get("staff"),
                                        resource_id=serializer.validated_data.get("resource"))
        return self._respond(booking)

    @extend_schema(tags=["bookings"], summary="Status and reschedule history",
                   responses={200: OpenApiTypes.OBJECT})
    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        booking = self.get_object()
        return Response({
            "status": s.StatusHistorySerializer(booking.status_history.select_related("changed_by"), many=True).data,
            "reschedules": s.RescheduleHistorySerializer(booking.reschedules.select_related("rescheduled_by"),
                                                         many=True).data,
        })

    @extend_schema(
        tags=["bookings"], summary="Calendar events in a time range (max 62 days)",
        parameters=[OpenApiParameter("start", OpenApiTypes.DATETIME, required=True),
                    OpenApiParameter("end", OpenApiTypes.DATETIME, required=True)],
        responses={200: s.CalendarEventSerializer(many=True)},
    )
    @action(detail=False, methods=["get"], pagination_class=None)
    def calendar(self, request):
        start = parse_datetime(request.query_params.get("start", "") or "")
        end = parse_datetime(request.query_params.get("end", "") or "")
        if not start or not end or end <= start:
            raise ValidationError({"start": ["Provide ISO start and end datetimes, end after start."]})
        if end - start > timedelta(days=62):
            raise ValidationError({"end": ["Range is limited to 62 days."]})
        qs = self.filter_queryset(self.get_queryset()).filter(start_datetime__lt=end, end_datetime__gt=start)
        return Response(s.CalendarEventSerializer(qs.order_by("start_datetime")[:2000], many=True).data)
