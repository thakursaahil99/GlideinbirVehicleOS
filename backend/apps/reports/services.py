"""
Dashboards and reports. Every query starts from a tenant scope:
Super Admin → all agencies (optionally one), agency users → their own agency.
Revenue = settled payments net of refunds, by payment date.
"""
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db.models import Count, DateField, DateTimeField, DecimalField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import Coalesce, TruncDate, TruncMonth
from django.utils import timezone

from apps.bookings.models import ACTIVE_STATUSES, Booking, BookingStatus
from apps.customers.models import AgencyCustomer, Customer
from apps.invoices.models import Invoice, InvoiceStatus
from apps.job_cards.models import JobCard, JobCardStatus
from apps.notifications.models import Notification
from apps.organizations.models import Organization, OrganizationStatus
from apps.payments.models import Payment
from apps.vehicles.models import Vehicle
from apps.vendors.models import WorkingHours

ZERO = Decimal("0")
NET = ExpressionWrapper(F("amount") - F("refunded_amount"), output_field=DecimalField(max_digits=14, decimal_places=2))
JOB_ACTIVE = (JobCardStatus.OPEN, JobCardStatus.INSPECTION, JobCardStatus.WORK_IN_PROGRESS,
              JobCardStatus.WAITING_APPROVAL)


class Scope:
    """Resolved tenant scope + filters for one request."""

    def __init__(self, *, organization_id=None, date_from=None, date_to=None, vehicle_type=None, service_id=None,
                 status=None):
        today = timezone.localdate()
        self.organization_id = organization_id
        self.date_to = date_to or today
        self.date_from = date_from or (self.date_to - timedelta(days=29))
        if self.date_from > self.date_to:
            self.date_from, self.date_to = self.date_to, self.date_from
        self.vehicle_type, self.service_id, self.status = vehicle_type, service_id, status

    @property
    def start_dt(self):
        return timezone.make_aware(datetime.combine(self.date_from, time.min))

    @property
    def end_dt(self):
        return timezone.make_aware(datetime.combine(self.date_to + timedelta(days=1), time.min))

    def org(self, qs, field="organization_id"):
        return qs.filter(**{field: self.organization_id}) if self.organization_id else qs

    def bookings(self, in_period=True):
        qs = self.org(Booking.objects.all())
        if in_period:
            qs = qs.filter(booking_date__range=(self.date_from, self.date_to))
        if self.vehicle_type:
            qs = qs.filter(vehicle__vehicle_type=self.vehicle_type)
        if self.service_id:
            qs = qs.filter(vendor_service__service_id=self.service_id)
        if self.status:
            qs = qs.filter(status=self.status)
        return qs

    def payments(self, in_period=True):
        qs = self.org(Payment.objects.settled())
        if in_period:
            qs = qs.filter(paid_at__gte=self.start_dt, paid_at__lt=self.end_dt)
        if self.vehicle_type:
            qs = qs.filter(booking__vehicle__vehicle_type=self.vehicle_type)
        if self.service_id:
            qs = qs.filter(booking__vendor_service__service_id=self.service_id)
        return qs

    def open_invoices(self):
        return self.org(Invoice.objects.filter(status=InvoiceStatus.ISSUED)).exclude(payment_status="PAID")


def _revenue(qs):
    return qs.aggregate(v=Coalesce(Sum(NET), ZERO))["v"]


def _pending(scope):
    total = scope.open_invoices().aggregate(t=Coalesce(Sum(F("total") - F("amount_paid")), ZERO))["t"]
    return max(total, ZERO)


def _series(qs, date_field, value=None, by_month=False):
    is_date = isinstance(qs.model._meta.get_field(date_field), DateField) and not isinstance(
        qs.model._meta.get_field(date_field), DateTimeField)
    if by_month:
        period = TruncMonth(date_field)
    elif is_date:
        # Already a date: group on it directly (TruncDate on a DateField breaks SQLite under USE_TZ).
        period = F(date_field)
    else:
        period = TruncDate(date_field)
    rows = qs.annotate(period=period).values("period").annotate(
        v=Coalesce(Sum(value), ZERO) if value is not None else Count("id")).order_by("period")
    return {(r["period"].date() if isinstance(r["period"], datetime) else r["period"]): r["v"] for r in rows}


def _fill_days(scope, values):
    out, d = [], scope.date_from
    while d <= scope.date_to:
        out.append({"date": d.isoformat(), "value": values.get(d, 0)})
        d += timedelta(days=1)
    return out


def revenue_series(scope):
    return _fill_days(scope, _series(scope.payments(), "paid_at", NET))


def bookings_series(scope):
    return _fill_days(scope, _series(scope.bookings(), "booking_date"))


def popular_services(scope, limit=8):
    return list(scope.bookings().exclude(status__in=[BookingStatus.CANCELLED, BookingStatus.REJECTED])
                .values(name=F("vendor_service__service__name")).annotate(bookings=Count("id"))
                .order_by("-bookings", "name")[:limit])


def cancellation_rate(scope):
    qs = scope.bookings()
    total = qs.count()
    cancelled = qs.filter(status=BookingStatus.CANCELLED).count()
    return {"total": total, "cancelled": cancelled, "rate": round(100 * cancelled / total, 1) if total else 0.0}


class DashboardService:
    @staticmethod
    def super_admin(scope):
        today = timezone.localdate()
        bookings_all = scope.bookings(in_period=False)
        orgs = scope.org(Organization.objects.all(), field="pk")
        agency_perf = list(
            scope.payments().values(name=F("organization__name")).annotate(revenue=Sum(NET)).order_by("-revenue")[:8])
        booking_counts = {r["name"]: r["n"] for r in scope.bookings().values(name=F("organization__name"))
                          .annotate(n=Count("id"))}
        for row in agency_perf:
            row["bookings"] = booking_counts.get(row["name"], 0)
        return {
            "stats": {
                "agencies_total": orgs.count(),
                "agencies_active": orgs.filter(status=OrganizationStatus.ACTIVE).count(),
                "agencies_pending": orgs.filter(status=OrganizationStatus.PENDING).count(),
                "customers": (Customer.objects.filter(agency_links__organization_id=scope.organization_id).distinct()
                              if scope.organization_id else Customer.objects.all()).count(),
                "vehicles": Vehicle.objects.filter(is_active=True).count(),
                "bookings_today": bookings_all.filter(booking_date=today).count(),
                "bookings_upcoming": bookings_all.filter(status__in=ACTIVE_STATUSES,
                                                         start_datetime__gte=timezone.now()).count(),
                "bookings_completed": scope.bookings().filter(status=BookingStatus.COMPLETED).count(),
                "bookings_cancelled": scope.bookings().filter(status=BookingStatus.CANCELLED).count(),
                "revenue": _revenue(scope.payments()),
                "pending_payments": _pending(scope),
            },
            "charts": {
                "revenue": revenue_series(scope),
                "bookings": bookings_series(scope),
                "agency_performance": agency_perf,
                "vehicle_types": list(scope.bookings().values(type=F("vehicle__vehicle_type"))
                                      .annotate(count=Count("id")).order_by("-count")),
                "popular_services": popular_services(scope),
                "cancellation": cancellation_rate(scope),
            },
            "period": {"from": scope.date_from.isoformat(), "to": scope.date_to.isoformat()},
        }

    @staticmethod
    def agency(scope):
        today = timezone.localdate()
        now = timezone.now()
        all_bookings = scope.bookings(in_period=False)
        month_start = today.replace(day=1)
        today_scope = Scope(organization_id=scope.organization_id, date_from=today, date_to=today)
        month_scope = Scope(organization_id=scope.organization_id, date_from=month_start, date_to=today)
        jobs = scope.org(JobCard.objects.all())
        return {
            "stats": {
                "bookings_today": all_bookings.filter(booking_date=today).exclude(
                    status__in=[BookingStatus.CANCELLED, BookingStatus.REJECTED]).count(),
                "bookings_upcoming": all_bookings.filter(status__in=ACTIVE_STATUSES, start_datetime__gte=now).count(),
                "bookings_pending": all_bookings.filter(status=BookingStatus.PENDING).count(),
                "jobs_active": jobs.filter(status__in=JOB_ACTIVE).count(),
                "jobs_completed": jobs.filter(status__in=[JobCardStatus.COMPLETED, JobCardStatus.CLOSED],
                                              completed_at__gte=scope.start_dt).count(),
                "revenue_today": _revenue(today_scope.payments()),
                "revenue_month": _revenue(month_scope.payments()),
                "pending_payments": _pending(scope),
                "customers": AgencyCustomer.objects.filter(organization_id=scope.organization_id).count(),
                "vehicles": Vehicle.objects.filter(
                    customer__agency_links__organization_id=scope.organization_id, is_active=True).count(),
            },
            "charts": {
                "revenue": revenue_series(scope),
                "bookings": bookings_series(scope),
                "popular_services": popular_services(scope),
                "staff_utilization": staff_performance(scope),
            },
            "today": [
                {"id": str(b.pk), "booking_number": b.booking_number, "start": b.start_datetime.isoformat(),
                 "status": b.status, "customer": b.customer.full_name, "service": b.vendor_service.service.name,
                 "vehicle": b.vehicle.registration_number}
                for b in all_bookings.filter(booking_date=today).select_related(
                    "customer", "vendor_service__service", "vehicle").order_by("start_datetime")[:20]
            ],
            "period": {"from": scope.date_from.isoformat(), "to": scope.date_to.isoformat()},
        }

    @staticmethod
    def customer(user):
        bookings = Booking.objects.filter(customer__user=user)
        now = timezone.now()
        upcoming = (bookings.filter(status__in=ACTIVE_STATUSES, start_datetime__gte=now)
                    .select_related("organization", "vendor_service__service", "vehicle").order_by("start_datetime")
                    .first())
        invoices = Invoice.objects.filter(customer__user=user, status=InvoiceStatus.ISSUED)
        return {
            "stats": {
                "vehicles": Vehicle.objects.filter(customer__user=user, is_active=True).count(),
                "bookings_upcoming": bookings.filter(status__in=ACTIVE_STATUSES, start_datetime__gte=now).count(),
                "bookings_previous": bookings.filter(start_datetime__lt=now).count(),
                "services_completed": bookings.filter(status=BookingStatus.COMPLETED).count(),
                "pending_payments": max(invoices.exclude(payment_status="PAID").aggregate(
                    t=Coalesce(Sum(F("total") - F("amount_paid")), ZERO))["t"], ZERO),
                "invoices": invoices.count(),
                "unread_notifications": Notification.objects.filter(recipient=user, channel="IN_APP",
                                                                    read_at__isnull=True).count(),
                "total_spent": _revenue(Payment.objects.settled().filter(customer__user=user)),
            },
            "upcoming_booking": None if upcoming is None else {
                "id": str(upcoming.pk), "booking_number": upcoming.booking_number,
                "start": upcoming.start_datetime.isoformat(), "status": upcoming.status,
                "agency": upcoming.organization.name, "service": upcoming.vendor_service.service.name,
                "vehicle": f"{upcoming.vehicle.brand} {upcoming.vehicle.model} ({upcoming.vehicle.registration_number})",
            },
        }


# ---------------------------------------------------------------------- reports
def staff_performance(scope):
    qs = scope.bookings().filter(assigned_staff__isnull=False)
    rows = (qs.values(staff=F("assigned_staff__full_name"))
            .annotate(bookings=Count("id"), completed=Count("id", filter=Q(status=BookingStatus.COMPLETED)),
                      minutes=Coalesce(Sum("duration_minutes", filter=~Q(status__in=[BookingStatus.CANCELLED,
                                                                                    BookingStatus.REJECTED])), 0))
            .order_by("-bookings"))
    return [{**r, "hours": round(r.pop("minutes") / 60, 1),
             "completion_rate": round(100 * r["completed"] / r["bookings"], 1) if r["bookings"] else 0.0}
            for r in rows]


def _open_minutes(organization_id, date_from, date_to):
    weekly = defaultdict(int)
    for wh in WorkingHours.objects.filter(organization_id=organization_id):
        weekly[wh.weekday] += (datetime.combine(date.min, wh.closes_at)
                               - datetime.combine(date.min, wh.opens_at)).seconds // 60
    total, d = 0, date_from
    while d <= date_to:
        total += weekly[d.weekday()]
        d += timedelta(days=1)
    return total


def agency_utilization(scope):
    orgs = scope.org(Organization.objects.filter(status=OrganizationStatus.ACTIVE), field="pk")
    booked = {r["organization_id"]: r["m"] for r in scope.bookings().exclude(
        status__in=[BookingStatus.CANCELLED, BookingStatus.REJECTED]).values("organization_id").annotate(
        m=Sum("duration_minutes"))}
    rows = []
    for org in orgs.order_by("name"):
        open_m = _open_minutes(org.pk, scope.date_from, scope.date_to)
        used = booked.get(org.pk, 0) or 0
        rows.append({"agency": org.name, "booked_hours": round(used / 60, 1), "open_hours": round(open_m / 60, 1),
                     "utilization_pct": round(100 * used / open_m, 1) if open_m else 0.0})
    return rows


def customer_retention(scope):
    qs = scope.bookings().filter(status=BookingStatus.COMPLETED).values("customer_id").annotate(n=Count("id"))
    customers = qs.count()
    returning = qs.filter(n__gte=2).count()
    return [{"customers_served": customers, "returning_customers": returning,
             "retention_pct": round(100 * returning / customers, 1) if customers else 0.0}]


def pending_payments_rows(scope):
    return [{"invoice": i.invoice_number, "agency": i.organization.name, "customer": i.customer.full_name,
             "invoice_date": i.invoice_date.isoformat(), "total": i.total, "paid": i.amount_paid,
             "balance": i.total - i.amount_paid, "status": i.payment_status}
            for i in scope.open_invoices().select_related("organization", "customer").order_by("invoice_date")[:2000]]


def growth(qs, field, scope, by_month):
    values = _series(qs, field, by_month=by_month)
    return [{"period": k.isoformat(), "count": v} for k, v in sorted(values.items())]


REPORTS = {
    # name: (audience, title, builder)
    "agency-revenue": ("admin", "Revenue by agency", lambda s: list(
        s.payments().values(agency=F("organization__name")).annotate(revenue=Sum(NET), payments=Count("id"))
        .order_by("-revenue"))),
    "service-revenue": ("both", "Revenue by service", lambda s: list(
        s.payments().filter(booking__isnull=False).values(service=F("booking__vendor_service__service__name"))
        .annotate(revenue=Sum(NET), payments=Count("id")).order_by("-revenue"))),
    "customer-growth": ("admin", "New customers per month", lambda s: growth(
        Customer.objects.filter(created_at__gte=s.start_dt, created_at__lt=s.end_dt), "created_at", s, True)),
    "booking-growth": ("admin", "Bookings per month", lambda s: growth(s.bookings(), "booking_date", s, True)),
    "cancellation-rate": ("both", "Cancellation rate", lambda s: [cancellation_rate(s)]),
    "agency-utilization": ("admin", "Agency utilization", agency_utilization),
    "popular-services": ("admin", "Popular services", lambda s: popular_services(s, limit=50)),
    "top-agencies": ("admin", "Top agencies", lambda s: list(
        s.bookings().filter(status=BookingStatus.COMPLETED).values(agency=F("organization__name"))
        .annotate(completed_bookings=Count("id")).order_by("-completed_bookings")[:20])),
    "pending-payments": ("both", "Pending payments", pending_payments_rows),
    "daily-revenue": ("agency", "Daily revenue", lambda s: [
        {"date": r["date"], "revenue": r["value"]} for r in revenue_series(s)]),
    "monthly-revenue": ("agency", "Monthly revenue", lambda s: [
        {"month": k.strftime("%Y-%m"), "revenue": v}
        for k, v in sorted(_series(s.payments(), "paid_at", NET, by_month=True).items())]),
    "staff-performance": ("agency", "Staff performance", staff_performance),
    "completion-rate": ("agency", "Completion rate", lambda s: [{
        "bookings": (t := s.bookings().exclude(status__in=ACTIVE_STATUSES).count()),
        "completed": (c := s.bookings().filter(status=BookingStatus.COMPLETED).count()),
        "completion_pct": round(100 * c / t, 1) if t else 0.0}]),
    "customer-retention": ("agency", "Customer retention", customer_retention),
}


def build_report(name, scope):
    audience, title, builder = REPORTS[name]
    rows = builder(scope)
    columns = list(rows[0].keys()) if rows else []
    return {"name": name, "title": title, "columns": columns, "rows": rows,
            "period": {"from": scope.date_from.isoformat(), "to": scope.date_to.isoformat()}}

