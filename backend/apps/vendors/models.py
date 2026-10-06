"""
Agency operations: booking settings, weekly working hours (multiple intervals per
day — gaps are breaks), holidays / emergency closures, special working dates and
bookable resources (bays, technicians, equipment).
"""
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import TenantModel


class Weekday(models.IntegerChoices):
    MONDAY = 0, "Monday"
    TUESDAY = 1, "Tuesday"
    WEDNESDAY = 2, "Wednesday"
    THURSDAY = 3, "Thursday"
    FRIDAY = 4, "Friday"
    SATURDAY = 5, "Saturday"
    SUNDAY = 6, "Sunday"


class AgencySettings(TenantModel):
    organization = models.OneToOneField("organizations.Organization", on_delete=models.CASCADE,
                                        related_name="booking_settings")
    slot_interval_minutes = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(5), MaxValueValidator(480)],
        help_text="Step between slot starts. Empty = service duration + buffer.",
    )
    buffer_minutes = models.PositiveSmallIntegerField(default=0, validators=[MaxValueValidator(240)],
                                                      help_text="Gap kept free after every booking.")
    booking_lead_time_minutes = models.PositiveIntegerField(default=60, validators=[MaxValueValidator(60 * 24 * 7)],
                                                            help_text="Earliest bookable slot from now.")
    max_advance_days = models.PositiveSmallIntegerField(default=30, validators=[MinValueValidator(1),
                                                                                MaxValueValidator(365)])
    cancellation_cutoff_hours = models.PositiveSmallIntegerField(
        default=2, validators=[MaxValueValidator(168)],
        help_text="Customers cannot cancel/reschedule closer than this to the start time.",
    )
    auto_confirm_bookings = models.BooleanField(default=False)
    additional_work_requires_approval = models.BooleanField(default=True)
    require_online_payment = models.BooleanField(default=False,
                                                 help_text="Customers pay (mock gateway) when booking.")

    class Meta:
        verbose_name_plural = "agency settings"

    def __str__(self):
        return f"Settings for {self.organization}"


class WorkingHours(TenantModel):
    weekday = models.PositiveSmallIntegerField(choices=Weekday.choices)
    opens_at = models.TimeField()
    closes_at = models.TimeField()

    class Meta:
        ordering = ("weekday", "opens_at")
        verbose_name_plural = "working hours"
        constraints = [
            models.CheckConstraint(condition=models.Q(closes_at__gt=models.F("opens_at")),
                                   name="working_hours_close_after_open"),
            models.CheckConstraint(condition=models.Q(weekday__gte=0, weekday__lte=6), name="working_hours_weekday"),
            models.UniqueConstraint(fields=["organization", "weekday", "opens_at"], name="working_hours_unique_start"),
        ]

    def __str__(self):
        return f"{self.get_weekday_display()} {self.opens_at:%H:%M}-{self.closes_at:%H:%M}"


class HolidayKind(models.TextChoices):
    HOLIDAY = "HOLIDAY", "Holiday"
    EMERGENCY_CLOSURE = "EMERGENCY_CLOSURE", "Emergency closure"


class Holiday(TenantModel):
    """Whole-day closure over an inclusive date range."""

    name = models.CharField(max_length=120)
    start_date = models.DateField()
    end_date = models.DateField()
    kind = models.CharField(max_length=20, choices=HolidayKind.choices, default=HolidayKind.HOLIDAY)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("start_date",)
        indexes = [models.Index(fields=["organization", "start_date", "end_date"], name="holiday_org_range_idx")]
        constraints = [
            models.CheckConstraint(condition=models.Q(end_date__gte=models.F("start_date")),
                                   name="holiday_end_after_start"),
        ]

    def __str__(self):
        return f"{self.name} ({self.start_date} → {self.end_date})"


class SpecialWorkingDay(TenantModel):
    """Overrides the weekly schedule for one date (e.g. open on a Sunday, or shorter hours)."""

    date = models.DateField()
    opens_at = models.TimeField()
    closes_at = models.TimeField()
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ("date", "opens_at")
        constraints = [
            models.CheckConstraint(condition=models.Q(closes_at__gt=models.F("opens_at")),
                                   name="special_day_close_after_open"),
            models.UniqueConstraint(fields=["organization", "date", "opens_at"], name="special_day_unique_start"),
        ]

    def __str__(self):
        return f"{self.date} {self.opens_at:%H:%M}-{self.closes_at:%H:%M}"


class ResourceType(models.TextChoices):
    BAY = "BAY", "Service bay"
    TECHNICIAN = "TECHNICIAN", "Technician"
    EQUIPMENT = "EQUIPMENT", "Equipment"
    OTHER = "OTHER", "Other"


class ServiceResource(TenantModel):
    """Something a booking occupies exclusively for its duration. Used in conflict checks."""

    name = models.CharField(max_length=120)
    resource_type = models.CharField(max_length=20, choices=ResourceType.choices)
    staff = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="resources", help_text="For technicians: the staff member.")
    description = models.TextField(blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ("resource_type", "name")
        constraints = [models.UniqueConstraint(fields=["organization", "name"], name="resource_unique_name")]
        indexes = [models.Index(fields=["organization", "resource_type", "active"], name="resource_lookup_idx")]

    def __str__(self):
        return f"{self.name} ({self.get_resource_type_display()})"
