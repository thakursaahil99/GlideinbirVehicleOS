from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models

from apps.core.models import TenantModel
from apps.organizations.models import gst_validator
from apps.vehicles.models import VehicleType


class Unit(models.TextChoices):
    PCS = "PCS", "Pieces"
    LITRE = "LITRE", "Litres"
    KG = "KG", "Kilograms"
    SET = "SET", "Sets"
    METRE = "METRE", "Metres"


class PartCategory(TenantModel):
    """Agency-defined grouping for parts (Engine, Brakes, Electrical, Oils…)."""

    name = models.CharField(max_length=80)
    description = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ("name",)
        verbose_name_plural = "part categories"
        constraints = [models.UniqueConstraint(fields=["organization", "name"], name="part_category_unique_name")]

    def __str__(self):
        return self.name


class Supplier(TenantModel):
    """A dealer or distributor the agency buys parts from."""

    name = models.CharField(max_length=150)
    contact_person = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    gst_number = models.CharField(max_length=15, blank=True, validators=[gst_validator])
    address = models.CharField(max_length=300, blank=True)
    notes = models.CharField(max_length=500, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)
        constraints = [models.UniqueConstraint(fields=["organization", "name"], name="supplier_unique_name")]

    def __str__(self):
        return self.name


class Part(TenantModel):
    name = models.CharField(max_length=150)
    sku = models.CharField(max_length=60)
    brand = models.CharField(max_length=80, blank=True)
    category = models.ForeignKey(PartCategory, null=True, blank=True, on_delete=models.SET_NULL, related_name="parts")
    preferred_supplier = models.ForeignKey(Supplier, null=True, blank=True, on_delete=models.SET_NULL,
                                           related_name="parts")
    hsn_code = models.CharField(max_length=8, blank=True, help_text="GST HSN code (4–8 digits)",
                                validators=[RegexValidator(r"^[0-9]{4,8}$", "HSN code must be 4–8 digits.")])
    rack_location = models.CharField(max_length=50, blank=True, help_text="Where it sits, e.g. Rack B · Shelf 3")
    universal = models.BooleanField(default=False, help_text="Fits every vehicle (bulbs, generic fluids…)")
    description = models.CharField(max_length=500, blank=True)
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"),
                                         validators=[MinValueValidator(Decimal("0"))])
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"),
                                        validators=[MinValueValidator(Decimal("0"))])
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("18.00"),
                                   validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))])
    stock_quantity = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    minimum_stock = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"),
                                        validators=[MinValueValidator(Decimal("0"))])
    unit = models.CharField(max_length=10, choices=Unit.choices, default=Unit.PCS)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(fields=["organization", "sku"], name="part_unique_sku"),
            # The last line of defence against overselling — stock can never go negative.
            models.CheckConstraint(condition=models.Q(stock_quantity__gte=0), name="part_stock_non_negative"),
            models.CheckConstraint(condition=models.Q(selling_price__gte=0, purchase_price__gte=0),
                                   name="part_prices_non_negative"),
        ]
        indexes = [models.Index(fields=["organization", "active", "name"], name="part_lookup_idx")]

    def __str__(self):
        return f"{self.name} ({self.sku})"

    @property
    def is_low_stock(self):
        return self.stock_quantity <= self.minimum_stock


class PartFitment(TenantModel):
    """
    One vehicle a part fits. Blank ``model`` means every model of ``brand``; blank
    ``vehicle_type`` matches any type; open year bounds match any year.
    """

    part = models.ForeignKey(Part, on_delete=models.CASCADE, related_name="fitments")
    vehicle_type = models.CharField(max_length=10, choices=VehicleType.choices, blank=True)
    brand = models.CharField(max_length=60)
    model = models.CharField(max_length=80, blank=True)
    year_from = models.PositiveSmallIntegerField(null=True, blank=True)
    year_to = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ("brand", "model")
        indexes = [models.Index(fields=["organization", "brand", "model"], name="fitment_lookup_idx")]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(year_from__isnull=True) | models.Q(year_to__isnull=True)
                | models.Q(year_from__lte=models.F("year_to")),
                name="fitment_year_range_valid",
            ),
        ]

    def __str__(self):
        years = f" {self.year_from or ''}–{self.year_to or ''}" if (self.year_from or self.year_to) else ""
        return f"{self.brand} {self.model or '(all models)'}{years}"


class TransactionType(models.TextChoices):
    PURCHASE = "PURCHASE", "Purchase"
    SALE = "SALE", "Sale"
    USED_IN_JOB = "USED_IN_JOB", "Used in job"
    ADJUSTMENT = "ADJUSTMENT", "Adjustment"
    RETURN = "RETURN", "Return"


class StockTransaction(TenantModel):
    """Ledger row. ``quantity`` is signed: + into stock, − out of stock."""

    part = models.ForeignKey(Part, on_delete=models.PROTECT, related_name="transactions")
    line_no = models.PositiveIntegerField(help_text="1, 2, 3… per part — assigned under the part row lock")
    transaction_type = models.CharField(max_length=12, choices=TransactionType.choices)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    balance_after = models.DecimalField(max_digits=12, decimal_places=2)
    supplier = models.ForeignKey(Supplier, null=True, blank=True, on_delete=models.PROTECT,
                                 related_name="stock_transactions", help_text="Who it was bought from (purchases)")
    job_card = models.ForeignKey("job_cards.JobCard", null=True, blank=True, on_delete=models.PROTECT,
                                 related_name="stock_transactions")
    reference = models.CharField(max_length=100, blank=True)
    note = models.CharField(max_length=300, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        # Timestamps can tie (coarse clocks); the per-part line number never does.
        ordering = ("part", "-line_no")
        indexes = [
            models.Index(fields=["part", "-created_at"], name="stock_tx_part_idx"),
            models.Index(fields=["organization", "transaction_type", "-created_at"], name="stock_tx_type_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=~models.Q(quantity=0), name="stock_tx_non_zero"),
            models.UniqueConstraint(fields=["part", "line_no"], name="stock_tx_unique_line"),
        ]
