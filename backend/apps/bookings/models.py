from django.conf import settings
from django.db import models

from apps.core.models import BaseModel, TenantModel
from apps.core.tenancy import TenantQuerySet


class BookingStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    CONFIRMED = "CONFIRMED", "Confirmed"
    ASSIGNED = "ASSIGNED", "Assigned"
    VEHICLE_RECEIVED = "VEHICLE_RECEIVED", "Vehicle received"
    IN_PROGRESS = "IN_PROGRESS", "In progress"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL", "Waiting for approval"
    COMPLETED = "COMPLETED", "Completed"
    CANCELLED = "CANCELLED", "Cancelled"
    REJECTED = "REJECTED", "Rejected"
    NO_SHOW = "NO_SHOW", "No show"


#: Statuses that occupy capacity and resources.
ACTIVE_STATUSES = (
    BookingStatus.PENDING, BookingStatus.CONFIRMED, BookingStatus.ASSIGNED, BookingStatus.VEHICLE_RECEIVED,
    BookingStatus.IN_PROGRESS, BookingStatus.WAITING_FOR_APPROVAL,
)
TERMINAL_STATUSES = (BookingStatus.COMPLETED, BookingStatus.CANCELLED, BookingStatus.REJECTED, BookingStatus.NO_SHOW)


class PaymentStatus(models.TextChoices):
    UNPAID = "UNPAID", "Unpaid"
    PARTIALLY_PAID = "PARTIALLY_PAID", "Partially paid"
    PAID = "PAID", "Paid"
    REFUNDED = "REFUNDED", "Refunded"


class BookingSource(models.TextChoices):
    ONLINE = "ONLINE", "Customer app"
    AGENCY = "AGENCY", "Created by agency"


class BookingQuerySet(TenantQuerySet):
    def for_user(self, user):
        if user is None or not getattr(user, "is_authenticated", False):
            return self.none()
        if user.is_customer:
            return self.filter(customer__user=user)
        qs = super().for_user(user)
        from apps.accounts.constants import Role

        if user.role == Role.AGENCY_STAFF:
            # Staff see bookings assigned to them only.
            qs = qs.filter(assigned_staff=user)
        return qs

    def active(self):
        return self.filter(status__in=ACTIVE_STATUSES)

    def overlapping(self, start, end):
        return self.filter(start_datetime__lt=end, end_datetime__gt=start)


class Booking(TenantModel):
    booking_number = models.CharField(max_length=20, unique=True)
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="bookings")
    vehicle = models.ForeignKey("vehicles.Vehicle", on_delete=models.PROTECT, related_name="bookings")
    vendor_service = models.ForeignKey("services.VendorService", on_delete=models.PROTECT, related_name="bookings")
    booking_date = models.DateField(help_text="Local date at the agency")
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField()
    status = models.CharField(max_length=24, choices=BookingStatus.choices, default=BookingStatus.PENDING)
    payment_status = models.CharField(max_length=16, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID)
    source = models.CharField(max_length=10, choices=BookingSource.choices, default=BookingSource.ONLINE)
    assigned_staff = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                       related_name="assigned_bookings")
    assigned_resource = models.ForeignKey("vendors.ServiceResource", null=True, blank=True,
                                          on_delete=models.PROTECT, related_name="bookings")
    customer_notes = models.TextField(blank=True, max_length=2000)
    internal_notes = models.TextField(blank=True, max_length=4000)
    pickup_requested = models.BooleanField(default=False)
    drop_requested = models.BooleanField(default=False)
    pickup_address = models.TextField(blank=True)
    # Snapshot at booking time so later price changes never alter an existing booking.
    quoted_price = models.DecimalField(max_digits=10, decimal_places=2)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2)
    duration_minutes = models.PositiveSmallIntegerField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    confirmed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name="+")
    cancellation_reason = models.TextField(blank=True)
    reminder_sent_at = models.DateTimeField(null=True, blank=True)

    objects = BookingQuerySet.as_manager()

    class Meta:
        ordering = ("-start_datetime",)
        indexes = [
            models.Index(fields=["organization", "start_datetime"], name="booking_org_start_idx"),
            models.Index(fields=["organization", "status"], name="booking_org_status_idx"),
            models.Index(fields=["vendor_service", "start_datetime"], name="booking_vs_start_idx"),
            models.Index(fields=["assigned_resource", "start_datetime"], name="booking_resource_start_idx"),
            models.Index(fields=["customer", "-start_datetime"], name="booking_customer_idx"),
            models.Index(fields=["vehicle", "start_datetime"], name="booking_vehicle_idx"),
            models.Index(fields=["booking_date"], name="booking_date_idx"),
            models.Index(fields=["end_datetime"], name="booking_end_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(end_datetime__gt=models.F("start_datetime")),
                                   name="booking_end_after_start"),
            models.CheckConstraint(condition=models.Q(status__in=BookingStatus.values), name="booking_status_valid"),
            models.CheckConstraint(condition=models.Q(quoted_price__gte=0), name="booking_price_non_negative"),
        ]

    def __str__(self):
        return self.booking_number

    @property
    def is_active(self):
        return self.status in ACTIVE_STATUSES


class BookingStatusHistory(BaseModel):
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="status_history")
    from_status = models.CharField(max_length=24, blank=True)
    to_status = models.CharField(max_length=24)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    note = models.TextField(blank=True)

    class Meta:
        ordering = ("created_at",)
        verbose_name_plural = "booking status history"


class BookingReschedule(BaseModel):
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="reschedules")
    old_start = models.DateTimeField()
    old_end = models.DateTimeField()
    new_start = models.DateTimeField()
    new_end = models.DateTimeField()
    old_resource = models.ForeignKey("vendors.ServiceResource", null=True, on_delete=models.SET_NULL, related_name="+")
    new_resource = models.ForeignKey("vendors.ServiceResource", null=True, on_delete=models.SET_NULL, related_name="+")
    reason = models.TextField(blank=True)
    rescheduled_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
                                       related_name="+")

    class Meta:
        ordering = ("created_at",)
