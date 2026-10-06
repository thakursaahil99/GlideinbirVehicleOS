from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import BaseModel, TenantModel
from apps.core.storage import UploadPath, media_storage
from apps.core.tenancy import TenantQuerySet
from apps.core.validators import ImageFileValidator


class JobCardStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    INSPECTION = "INSPECTION", "Inspection"
    WORK_IN_PROGRESS = "WORK_IN_PROGRESS", "Work in progress"
    WAITING_APPROVAL = "WAITING_APPROVAL", "Waiting approval"
    COMPLETED = "COMPLETED", "Completed"
    CLOSED = "CLOSED", "Closed"


class FuelLevel(models.TextChoices):
    EMPTY = "EMPTY", "Empty"
    QUARTER = "QUARTER", "1/4"
    HALF = "HALF", "1/2"
    THREE_QUARTER = "THREE_QUARTER", "3/4"
    FULL = "FULL", "Full"


class JobCardQuerySet(TenantQuerySet):
    def for_user(self, user):
        if user is None or not getattr(user, "is_authenticated", False):
            return self.none()
        if user.is_customer:
            return self.filter(customer__user=user)
        qs = super().for_user(user)
        from apps.accounts.constants import Role

        if user.role == Role.AGENCY_STAFF:
            qs = qs.filter(booking__assigned_staff=user)
        return qs


class JobCard(TenantModel):
    job_card_number = models.CharField(max_length=20, unique=True)
    booking = models.OneToOneField("bookings.Booking", on_delete=models.PROTECT, related_name="job_card")
    vehicle = models.ForeignKey("vehicles.Vehicle", on_delete=models.PROTECT, related_name="job_cards")
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="job_cards")
    status = models.CharField(max_length=20, choices=JobCardStatus.choices, default=JobCardStatus.OPEN)
    inspection_notes = models.TextField(blank=True)
    vehicle_condition = models.TextField(blank=True)
    odometer = models.PositiveIntegerField(null=True, blank=True)
    fuel_level = models.CharField(max_length=16, choices=FuelLevel.choices, blank=True)
    existing_damage = models.TextField(blank=True)
    customer_requests = models.TextField(blank=True)
    technician_notes = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    objects = JobCardQuerySet.as_manager()

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["organization", "status"], name="job_card_org_status_idx"),
            models.Index(fields=["vehicle", "-created_at"], name="job_card_vehicle_idx"),
        ]

    def __str__(self):
        return self.job_card_number


class InspectionArea(models.TextChoices):
    EXTERIOR = "EXTERIOR", "Exterior"
    INTERIOR = "INTERIOR", "Interior"
    TYRES = "TYRES", "Tyres"
    BRAKES = "BRAKES", "Brakes"
    LIGHTS = "LIGHTS", "Lights"
    ENGINE = "ENGINE", "Engine"
    BATTERY = "BATTERY", "Battery"
    AC = "AC", "AC"
    FLUIDS = "FLUIDS", "Fluids"
    OTHER = "OTHER", "Other"


class InspectionStage(models.TextChoices):
    BEFORE = "BEFORE", "Before service"
    AFTER = "AFTER", "After service"


class InspectionResult(models.TextChoices):
    OK = "OK", "OK"
    ATTENTION = "ATTENTION", "Needs attention"
    REPLACE = "REPLACE", "Replace"
    NOT_CHECKED = "NOT_CHECKED", "Not checked"


class InspectionItem(BaseModel):
    job_card = models.ForeignKey(JobCard, on_delete=models.CASCADE, related_name="inspection_items")
    area = models.CharField(max_length=12, choices=InspectionArea.choices)
    stage = models.CharField(max_length=8, choices=InspectionStage.choices, default=InspectionStage.BEFORE)
    result = models.CharField(max_length=12, choices=InspectionResult.choices, default=InspectionResult.NOT_CHECKED)
    notes = models.TextField(blank=True)
    inspected_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ("stage", "area")
        constraints = [models.UniqueConstraint(fields=["job_card", "area", "stage"], name="inspection_unique_area")]


class PhotoStage(models.TextChoices):
    BEFORE = "BEFORE", "Before service"
    AFTER = "AFTER", "After service"
    OTHER = "OTHER", "Other"


class JobCardPhoto(BaseModel):
    job_card = models.ForeignKey(JobCard, on_delete=models.CASCADE, related_name="photos")
    stage = models.CharField(max_length=8, choices=PhotoStage.choices, default=PhotoStage.BEFORE)
    image = models.ImageField(upload_to=UploadPath("job_cards/photos"), storage=media_storage,
                              validators=[ImageFileValidator(max_width=8000, max_height=8000)])
    caption = models.CharField(max_length=200, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ("stage", "created_at")


class AdditionalWorkStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    CANCELLED = "CANCELLED", "Cancelled"


class AdditionalWorkRequest(BaseModel):
    job_card = models.ForeignKey(JobCard, on_delete=models.CASCADE, related_name="additional_work")
    description = models.TextField(max_length=2000)
    estimated_cost = models.DecimalField(max_digits=10, decimal_places=2,
                                         validators=[MinValueValidator(Decimal("0"))])
    status = models.CharField(max_length=10, choices=AdditionalWorkStatus.choices,
                              default=AdditionalWorkStatus.PENDING)
    customer_response = models.TextField(blank=True)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    responded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name="+")
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    auto_approved = models.BooleanField(default=False)

    class Meta:
        ordering = ("created_at",)
        constraints = [models.CheckConstraint(condition=models.Q(estimated_cost__gte=0),
                                              name="additional_work_cost_non_negative")]


class JobCardPart(BaseModel):
    """A part consumed on a job card — always backed by a USED_IN_JOB stock transaction."""

    job_card = models.ForeignKey(JobCard, on_delete=models.CASCADE, related_name="parts_used")
    part = models.ForeignKey("inventory.Part", on_delete=models.PROTECT, related_name="job_usages")
    quantity = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    returned_quantity = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2)
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ("created_at",)
        constraints = [
            models.CheckConstraint(condition=models.Q(returned_quantity__lte=models.F("quantity")),
                                   name="job_part_return_lte_used"),
        ]

    @property
    def net_quantity(self):
        return self.quantity - self.returned_quantity
