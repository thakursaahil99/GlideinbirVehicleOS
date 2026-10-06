from datetime import timedelta

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.tenancy import get_user_organization_id
from apps.services.models import VendorService

from .services import AvailabilityService, parse_day


def _vendor_service_for(request):
    vs_id = request.query_params.get("vendor_service")
    if not vs_id:
        raise ValidationError({"vendor_service": ["This query parameter is required."]})
    qs = VendorService.objects.select_related("service", "organization")
    try:
        vs = qs.filter(pk=vs_id).first()
    except Exception as exc:  # malformed UUID  # noqa: BLE001
        raise NotFound() from exc
    if vs is None:
        raise NotFound()
    user = request.user
    own_agency = get_user_organization_id(user) == vs.organization_id
    # Customers see only online-bookable offerings; agency staff also see their own offline ones.
    if not (user.is_super_admin or own_agency or VendorService.objects.bookable().filter(pk=vs.pk).exists()):
        raise NotFound()
    return vs, own_agency


def _slot_json(slot):
    return {"start": slot.start.isoformat(), "end": slot.end.isoformat(), "available": slot.available,
            "remaining": slot.remaining, "reason": slot.reason}


class SlotsView(APIView):
    @extend_schema(
        tags=["availability"], summary="Bookable time slots for one day (computed by the backend)",
        parameters=[OpenApiParameter("vendor_service", OpenApiTypes.UUID, required=True),
                    OpenApiParameter("date", OpenApiTypes.DATE, required=True)],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        vs, own_agency = _vendor_service_for(request)
        day = parse_day(request.query_params.get("date"))
        service = AvailabilityService(vs, enforce_lead_time=not own_agency)
        service.validate_day(day)
        slots = service.get_slots(day)
        return Response({
            "date": day.isoformat(), "timezone": str(service.tz), "vendor_service": str(vs.pk),
            "duration_minutes": vs.duration, "slots": [_slot_json(s) for s in slots],
        })


class DaysView(APIView):
    @extend_schema(
        tags=["availability"], summary="Per-day availability summary for a date range (max 31 days)",
        parameters=[OpenApiParameter("vendor_service", OpenApiTypes.UUID, required=True),
                    OpenApiParameter("start", OpenApiTypes.DATE, description="Defaults to today"),
                    OpenApiParameter("days", OpenApiTypes.INT, description="Default 14, max 31")],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        vs, own_agency = _vendor_service_for(request)
        service = AvailabilityService(vs, enforce_lead_time=not own_agency)
        start = parse_day(request.query_params["start"]) if request.query_params.get("start") else service.today()
        try:
            days = max(1, min(int(request.query_params.get("days", 14)), 31))
        except ValueError:
            days = 14
        result = service.get_slots_for_range(start, start + timedelta(days=days - 1))
        first, last = service.window()
        return Response({
            "timezone": str(service.tz), "window": {"first": first.isoformat(), "last": last.isoformat()},
            "days": [{"date": d.isoformat(), "bookable": first <= d <= last,
                      "available_slots": sum(1 for s in slots if s.available), "total_slots": len(slots)}
                     for d, slots in sorted(result.items())],
        })
