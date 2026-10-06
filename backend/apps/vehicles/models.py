import re

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import BaseModel, TenantModel
from apps.core.storage import UploadPath, media_storage
from apps.core.tenancy import get_user_organization_id
from apps.core.validators import DocumentFileValidator


class VehicleType(models.TextChoices):
    CAR = "CAR", "Car"
    BIKE = "BIKE", "Bike"
    SCOOTER = "SCOOTER", "Scooter"
    EV = "EV", "Electric vehicle"
    OTHER = "OTHER", "Other"


class FuelType(models.TextChoices):
    PETROL = "PETROL", "Petrol"
    DIESEL = "DIESEL", "Diesel"
    CNG = "CNG", "CNG"
    LPG = "LPG", "LPG"
    ELECTRIC = "ELECTRIC", "Electric"
    HYBRID = "HYBRID", "Hybrid"
    OTHER = "OTHER", "Other"


def normalize_registration(value):
    """'mh 12-ab 1234' → 'MH12AB1234' so searches and uniqueness are format-independent."""
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


class VehicleQuerySet(models.QuerySet):
    def for_user(self, user):
        if user is None or not getattr(user, "is_authenticated", False):
            return self.none()
        if user.is_super_admin:
            return self
        if user.is_customer:
            return self.filter(customer__user=user)
        org_id = get_user_organization_id(user)
        if org_id is None:
            return self.none()
        return self.filter(customer__agency_links__organization_id=org_id)

    def active(self):
        return self.filter(is_active=True)


class Vehicle(BaseModel):
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="vehicles")
    vehicle_type = models.CharField(max_length=10, choices=VehicleType.choices)
    brand = models.CharField(max_length=60)
    model = models.CharField(max_length=80)
    variant = models.CharField(max_length=80, blank=True)
    registration_number = models.CharField(max_length=20)
    vin = models.CharField(max_length=17, blank=True)
    chassis_number = models.CharField(max_length=30, blank=True)
    engine_number = models.CharField(max_length=30, blank=True)
    fuel_type = models.CharField(max_length=10, choices=FuelType.choices, default=FuelType.PETROL)
    manufacturing_year = models.PositiveSmallIntegerField(null=True, blank=True,
                                                          validators=[MinValueValidator(1950)])
    color = models.CharField(max_length=40, blank=True)
    odometer = models.PositiveIntegerField(null=True, blank=True, help_text="Kilometres")
    insurance_expiry = models.DateField(null=True, blank=True)
    registration_expiry = models.DateField(null=True, blank=True)
    pollution_expiry = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, help_text="Archived vehicles stay in service history.")

    objects = VehicleQuerySet.as_manager()

    class Meta:
        ordering = ("brand", "model")
        indexes = [
            models.Index(fields=["registration_number"], name="vehicle_registration_idx"),
            models.Index(fields=["vin"], name="vehicle_vin_idx"),
            models.Index(fields=["customer", "is_active"], name="vehicle_customer_idx"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["customer", "registration_number"], condition=models.Q(is_active=True),
                                    name="vehicle_unique_registration_per_customer"),
            models.UniqueConstraint(fields=["customer", "vin"],
                                    condition=models.Q(is_active=True) & ~models.Q(vin=""),
                                    name="vehicle_unique_vin_per_customer"),
            models.CheckConstraint(condition=models.Q(vehicle_type__in=VehicleType.values), name="vehicle_type_valid"),
        ]

    def __str__(self):
        return f"{self.brand} {self.model} ({self.registration_number})"

    def save(self, *args, **kwargs):
        self.registration_number = normalize_registration(self.registration_number)
        self.vin = (self.vin or "").strip().upper()
        super().save(*args, **kwargs)


class DocumentKind(models.TextChoices):
    RC = "RC", "Registration certificate"
    INSURANCE = "INSURANCE", "Insurance"
    PUC = "PUC", "Pollution certificate"
    PHOTO = "PHOTO", "Photo"
    OTHER = "OTHER", "Other"


class VehicleDocument(BaseModel):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="documents")
    kind = models.CharField(max_length=12, choices=DocumentKind.choices, default=DocumentKind.OTHER)
    title = models.CharField(max_length=120, blank=True)
    file = models.FileField(upload_to=UploadPath("vehicles/documents"), storage=media_storage,
                            validators=[DocumentFileValidator()])
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ("-created_at",)



class VehicleModel(TenantModel):
    """
    An agency's catalogue of vehicle models it sells or services (e.g. a newly launched scooter),
    with the showroom stock on hand.
    """

    vehicle_type = models.CharField(max_length=10, choices=VehicleType.choices, default=VehicleType.SCOOTER)
    brand = models.CharField(max_length=60)
    name = models.CharField(max_length=80, help_text="Model name, e.g. Jupiter 125")
    variant = models.CharField(max_length=80, blank=True, help_text="e.g. Disc, SmartXonnect")
    launch_year = models.PositiveSmallIntegerField(null=True, blank=True)
    fuel_type = models.CharField(max_length=10, choices=FuelType.choices, default=FuelType.PETROL)
    engine_cc = models.PositiveIntegerField(null=True, blank=True, help_text="Engine cc (blank for EVs)")
    colours = models.CharField(max_length=200, blank=True, help_text="Comma-separated colours")
    ex_showroom_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True,
                                            validators=[MinValueValidator(0)])
    stock_quantity = models.PositiveIntegerField(default=0)
    minimum_stock = models.PositiveIntegerField(default=0, help_text="Alert when stock falls to this level")
    is_active = models.BooleanField(default=True)
    notes = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ("brand", "name", "variant")
        constraints = [
            models.UniqueConstraint(fields=["organization", "brand", "name", "variant"],
                                    name="vehicle_model_unique_per_agency"),
        ]

    def __str__(self):
        return " ".join(filter(None, [self.brand, self.name, self.variant]))

    @property
    def is_low_stock(self):
        return self.stock_quantity <= self.minimum_stock


class VehicleSale(TenantModel):
    """One unit of a catalogue model sold to a buyer. Recording a sale takes one unit out of stock."""

    vehicle_model = models.ForeignKey(VehicleModel, on_delete=models.PROTECT, related_name="sales")
    customer = models.ForeignKey("customers.Customer", null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="vehicle_purchases")
    buyer_name = models.CharField(max_length=150)
    buyer_phone = models.CharField(max_length=16)
    buyer_email = models.EmailField(blank=True)
    buyer_address = models.CharField(max_length=300, blank=True)
    colour = models.CharField(max_length=40, blank=True)
    chassis_number = models.CharField(max_length=40, blank=True)
    engine_number = models.CharField(max_length=40, blank=True)
    registration_number = models.CharField(max_length=20, blank=True)
    sale_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    payment_mode = models.CharField(max_length=20, blank=True, help_text="Cash, UPI, Finance…")
    invoice_number = models.CharField(max_length=40, blank=True)
    sold_on = models.DateField()
    sold_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
                                related_name="vehicle_sales")
    notes = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ("-sold_on", "-created_at")

    def __str__(self):
        return f"{self.vehicle_model} → {self.buyer_name}"
