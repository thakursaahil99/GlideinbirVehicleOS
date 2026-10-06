"""
AvailabilityService — the single source of truth for bookable slots.

Slot generation considers: working hours (multiple intervals per weekday),
special working dates, holidays / emergency closures, the vendor service's
status, duration and capacity, the agency's buffer, lead time and booking
window, existing bookings, and free resources of the required type.

Example: a 120-minute service on a 09:00–13:00 / 14:00–19:00 day with no buffer
yields 09:00, 11:00, 14:00, 16:00 (18:00 would end after closing).

BookingService re-runs ``check_slot`` inside a row lock at booking time; the
frontend is never the final source of availability.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from django.db.models import Q
from django.utils import timezone

from apps.bookings.models import ACTIVE_STATUSES, Booking
from apps.core.exceptions import BusinessRuleViolation
from apps.organizations.models import organization_tz
from apps.vendors.models import Holiday, ServiceResource, SpecialWorkingDay, WorkingHours
from apps.vendors.services import get_agency_settings

MAX_RANGE_DAYS = 31


@dataclass
class Slot:
    start: datetime
    end: datetime
    available: bool
    remaining: int
    reason: str = ""
    free_resource_ids: list = field(default_factory=list)


class SlotUnavailable(BusinessRuleViolation):
    status_code = 409
    error_code = "BOOKING_SLOT_UNAVAILABLE"
    default_detail = "Selected time slot is no longer available."


class AvailabilityService:
    def __init__(self, vendor_service, *, now=None, enforce_lead_time=True):
        self.vs = vendor_service
        self.org = vendor_service.organization
        self.tz = organization_tz(self.org)
        self.settings = get_agency_settings(self.org)
        self.now = now or timezone.now()
        self.enforce_lead_time = enforce_lead_time
        self.duration = timedelta(minutes=vendor_service.duration)
        self.buffer = timedelta(minutes=self.settings.buffer_minutes)
        step_minutes = self.settings.slot_interval_minutes
        self.step = timedelta(minutes=step_minutes) if step_minutes else self.duration + self.buffer

    # ------------------------------------------------------------------ helpers
    def today(self):
        return self.now.astimezone(self.tz).date()

    def ensure_bookable(self):
        if not self.org.can_receive_bookings:
            raise BusinessRuleViolation("This agency is not accepting bookings.", code="VENDOR_NOT_ACTIVE")
        if not (self.vs.active and self.vs.service.active):
            raise BusinessRuleViolation("This service is not available.", code="SERVICE_INACTIVE")

    def window(self):
        first = self.today()
        return first, first + timedelta(days=self.settings.max_advance_days)

    def validate_day(self, day):
        first, last = self.window()
        if day < first:
            raise BusinessRuleViolation("Date is in the past.", code="DATE_IN_PAST")
        if day > last:
            raise BusinessRuleViolation(f"Bookings open at most {self.settings.max_advance_days} days ahead.",
                                        code="DATE_TOO_FAR")

    def _combine(self, day, t):
        return datetime.combine(day, t, tzinfo=self.tz)

    # ------------------------------------------------------------------ schedule
    def opening_intervals(self, days):
        """{day: [(open_dt, close_dt), ...]} for each requested day, honouring closures and special days."""
        days = list(days)
        if not days:
            return {}
        lo, hi = min(days), max(days)
        closed = set()
        for h in Holiday.objects.filter(organization=self.org, start_date__lte=hi, end_date__gte=lo):
            d = max(h.start_date, lo)
            while d <= min(h.end_date, hi):
                closed.add(d)
                d += timedelta(days=1)
        special = {}
        for sp in SpecialWorkingDay.objects.filter(organization=self.org, date__range=(lo, hi)):
            special.setdefault(sp.date, []).append((sp.opens_at, sp.closes_at))
        weekly = {}
        for wh in WorkingHours.objects.filter(organization=self.org):
            weekly.setdefault(wh.weekday, []).append((wh.opens_at, wh.closes_at))

        result = {}
        for d in days:
            if d in closed:
                result[d] = []
                continue
            intervals = special.get(d, weekly.get(d.weekday(), []))
            result[d] = sorted((self._combine(d, o), self._combine(d, c)) for o, c in intervals)
        return result

    def candidate_starts(self, intervals):
        for open_dt, close_dt in intervals:
            start = open_dt
            while start + self.duration <= close_dt:
                yield start
                start += self.step

    # ------------------------------------------------------------------ occupancy
    def _occupancy(self, range_start, range_end, exclude_booking_id=None):
        """Active bookings that could collide with slots in the range (padded by the buffer)."""
        lo, hi = range_start - self.buffer, range_end + self.buffer
        qs = Booking.objects.filter(organization=self.org, status__in=ACTIVE_STATUSES,
                                    start_datetime__lt=hi, end_datetime__gt=lo)
        resource_type = self.vs.required_resource_type
        if resource_type:
            qs = qs.filter(Q(vendor_service=self.vs) | Q(assigned_resource__resource_type=resource_type))
        else:
            qs = qs.filter(vendor_service=self.vs)
        if exclude_booking_id:
            qs = qs.exclude(pk=exclude_booking_id)
        return list(qs.values("vendor_service_id", "assigned_resource_id", "start_datetime", "end_datetime"))

    def _resources(self):
        if not self.vs.required_resource_type:
            return []
        return list(ServiceResource.objects.filter(organization=self.org, active=True,
                                                   resource_type=self.vs.required_resource_type)
                    .order_by("name").values_list("id", flat=True))

    def _evaluate(self, start, bookings, resource_ids):
        end = start + self.duration
        # A booking blocks [its start - buffer, its end + buffer).
        clash = [b for b in bookings
                 if b["start_datetime"] < end + self.buffer and b["end_datetime"] + self.buffer > start]
        same_service = sum(1 for b in clash if b["vendor_service_id"] == self.vs.id)
        remaining = self.vs.capacity - same_service
        free = []
        if self.vs.required_resource_type:
            busy = {b["assigned_resource_id"] for b in clash if b["assigned_resource_id"]}
            free = [r for r in resource_ids if r not in busy]
            remaining = min(remaining, len(free))
        reason = ""
        if self.enforce_lead_time and start < self.now + timedelta(minutes=self.settings.booking_lead_time_minutes):
            reason, remaining = "TOO_SOON", 0
        elif start < self.now:
            reason, remaining = "PAST", 0
        elif remaining <= 0:
            reason = "NO_RESOURCE" if self.vs.required_resource_type and not free else "FULL"
        return Slot(start=start, end=end, available=remaining > 0, remaining=max(remaining, 0), reason=reason,
                    free_resource_ids=free)

    # ------------------------------------------------------------------ public API
    def get_slots(self, day, *, exclude_booking_id=None):
        return self.get_slots_for_range(day, day, exclude_booking_id=exclude_booking_id)[day]

    def get_slots_for_range(self, first_day, last_day, *, exclude_booking_id=None):
        self.ensure_bookable()
        if (last_day - first_day).days > MAX_RANGE_DAYS:
            raise BusinessRuleViolation(f"Range is limited to {MAX_RANGE_DAYS} days.", code="RANGE_TOO_LARGE")
        win_first, win_last = self.window()
        days = [first_day + timedelta(days=i) for i in range((last_day - first_day).days + 1)]
        in_window = [d for d in days if win_first <= d <= win_last]
        intervals = self.opening_intervals(in_window)
        result = {d: [] for d in days}
        if not in_window:
            return result
        range_start = self._combine(min(in_window), datetime.min.time())
        range_end = self._combine(max(in_window) + timedelta(days=1), datetime.min.time())
        bookings = self._occupancy(range_start, range_end, exclude_booking_id)
        resource_ids = self._resources()
        for d in in_window:
            slots = [self._evaluate(s, bookings, resource_ids) for s in self.candidate_starts(intervals[d])]
            result[d] = [s for s in slots if s.reason not in ("PAST", "TOO_SOON")]
        return result

    def check_slot(self, start, *, exclude_booking_id=None):
        """
        Validate that ``start`` is a generated, currently free slot. Returns the
        Slot (with free resource ids). Raises SlotUnavailable otherwise.
        Call inside the booking transaction, after taking the row locks.
        """
        self.ensure_bookable()
        if timezone.is_naive(start):
            raise BusinessRuleViolation("Datetimes must include a timezone offset.", code="NAIVE_DATETIME")
        day = start.astimezone(self.tz).date()
        self.validate_day(day)
        starts = set(self.candidate_starts(self.opening_intervals([day])[day]))
        if start not in starts:
            raise SlotUnavailable("This time is outside the agency's bookable slots.")
        slot = self._evaluate(start, self._occupancy(start, start + self.duration, exclude_booking_id),
                              self._resources())
        if not slot.available:
            raise SlotUnavailable(details={"reason": slot.reason})
        return slot


def parse_day(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise BusinessRuleViolation("Use YYYY-MM-DD dates.", code="INVALID_DATE") from exc
