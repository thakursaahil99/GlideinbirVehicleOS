from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import BaseModel, TenantModel
from apps.core.tenancy import TenantQuerySet
from apps.vendors.models import ResourceType


class ServiceCategory(models.TextChoices):
    MAINTENANCE = "MAINTENANCE", "Maintenance"
    REPAIR = "REPAIR", "Repair"
    CLEANING = "CLEANING", "Cleaning & detailing"
    TYRES_WHEELS = "TYRES_WHEELS", "Tyres & wheels"
    ELECTRICAL = "ELECTRICAL", "Electrical & battery"
    DIAGNOSTICS = "DIAGNOSTICS", "Diagnostics"
    ASSISTANCE = "ASSISTANCE", "Assistance"
    EMERGENCY = "EMERGENCY", "Emergency"


class Service(BaseModel):
    """Global catalog entry, managed by the Super Admin."""

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    category = models.CharField(max_length=20, choices=ServiceCategory.choices)
    description = models.TextField(blank=True)
    supported_vehicle_types = models.JSONField(default=list, help_text="List of VehicleType values.")
    default_duration = models.PositiveSmallIntegerField(
        help_text="Minutes", validators=[MinValueValidator(5), MaxValueValidator(60 * 24)])
    base_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    tax = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("18.00"),
                              validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
                              help_text="GST rate in percent.")
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ("category", "name")
        indexes = [models.Index(fields=["active", "category"], name="service_active_category_idx")]
        constraints = [
            models.CheckConstraint(condition=models.Q(base_price__gte=0), name="service_price_non_negative"),
            models.CheckConstraint(condition=models.Q(tax__gte=0, tax__lte=100), name="service_tax_range"),
            models.CheckConstraint(condition=models.Q(default_duration__gte=5), name="service_duration_min"),
        ]

    def __str__(self):
        return self.name


class VendorServiceQuerySet(TenantQuerySet):
    def bookable(self):
        """Active offering of an active catalog service, open for online booking, at an ACTIVE agency."""
        return self.filter(active=True, online_booking_enabled=True, service__active=True,
                           organization__status="ACTIVE")


class VendorService(TenantModel):
    """An agency's offering of a catalog service with its own price, duration and capacity."""

    service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name="vendor_offerings")
    custom_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                       validators=[MinValueValidator(Decimal("0"))])
    custom_duration = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Minutes",
                                                       validators=[MinValueValidator(5), MaxValueValidator(60 * 24)])
    capacity = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(50)],
                                                help_text="Bookings that can run in parallel in one slot.")
    required_resource_type = models.CharField(
        max_length=20, choices=ResourceType.choices, blank=True,
        help_text="If set, every booking reserves one free resource of this type (e.g. a bay).",
    )
    active = models.BooleanField(default=True)
    pickup_available = models.BooleanField(default=False)
    drop_available = models.BooleanField(default=False)
    online_booking_enabled = models.BooleanField(default=True)
    description = models.TextField(blank=True)

    objects = VendorServiceQuerySet.as_manager()

    class Meta:
        ordering = ("service__name",)
        constraints = [
            models.UniqueConstraint(fields=["organization", "service"], name="vendor_service_unique"),
            models.CheckConstraint(condition=models.Q(capacity__gte=1), name="vendor_service_capacity_min"),
            models.CheckConstraint(condition=models.Q(custom_price__isnull=True) | models.Q(custom_price__gte=0),
                                   name="vendor_service_price_non_negative"),
        ]
        indexes = [models.Index(fields=["organization", "active"], name="vendor_service_org_active_idx")]

    def __str__(self):
        return f"{self.service} @ {self.organization}"

    @property
    def price(self):
        return self.custom_price if self.custom_price is not None else self.service.base_price

    @property
    def duration(self):
        return self.custom_duration or self.service.default_duration

    @property
    def tax_rate(self):
        return self.service.tax
