from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import TenantModel


class Unit(models.TextChoices):
    PCS = "PCS", "Pieces"
    LITRE = "LITRE", "Litres"
    KG = "KG", "Kilograms"
    SET = "SET", "Sets"
    METRE = "METRE", "Metres"


class Part(TenantModel):
    name = models.CharField(max_length=150)
    sku = models.CharField(max_length=60)
    brand = models.CharField(max_length=80, blank=True)
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
