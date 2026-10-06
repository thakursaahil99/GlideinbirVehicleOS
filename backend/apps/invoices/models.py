from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import BaseModel, TenantModel
from apps.core.storage import UploadPath, media_storage
from apps.core.tenancy import TenantQuerySet


class InvoiceStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    ISSUED = "ISSUED", "Issued"
    VOID = "VOID", "Void"


class InvoiceQuerySet(TenantQuerySet):
    def for_user(self, user):
        if user is not None and getattr(user, "is_authenticated", False) and user.is_customer:
            return self.filter(customer__user=user).exclude(status=InvoiceStatus.DRAFT)
        return super().for_user(user)


class Invoice(TenantModel):
    invoice_number = models.CharField(max_length=20, unique=True)
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="invoices")
    booking = models.OneToOneField("bookings.Booking", null=True, blank=True, on_delete=models.PROTECT,
                                   related_name="invoice")
    status = models.CharField(max_length=8, choices=InvoiceStatus.choices, default=InvoiceStatus.ISSUED)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"),
                                   validators=[MinValueValidator(Decimal("0"))])
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    payment_status = models.CharField(max_length=16, default="UNPAID")
    invoice_date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    pdf = models.FileField(upload_to=UploadPath("invoices/pdfs"), storage=media_storage, blank=True)
    issued_at = models.DateTimeField(null=True, blank=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")

    objects = InvoiceQuerySet.as_manager()

    class Meta:
        ordering = ("-invoice_date", "-created_at")
        indexes = [
            models.Index(fields=["organization", "invoice_date"], name="invoice_org_date_idx"),
            models.Index(fields=["organization", "payment_status"], name="invoice_org_paystatus_idx"),
            models.Index(fields=["customer", "-invoice_date"], name="invoice_customer_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(total__gte=0), name="invoice_total_non_negative"),
            models.CheckConstraint(condition=models.Q(discount__gte=0), name="invoice_discount_non_negative"),
        ]

    def __str__(self):
        return self.invoice_number

    @property
    def balance_due(self):
        return max(self.total - self.amount_paid, Decimal("0"))


class ItemType(models.TextChoices):
    SERVICE = "SERVICE", "Service"
    PART = "PART", "Part"
    ADDITIONAL_WORK = "ADDITIONAL_WORK", "Additional work"
    LABOUR = "LABOUR", "Labour"
    OTHER = "OTHER", "Other"


class InvoiceItem(BaseModel):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="items")
    item_type = models.CharField(max_length=16, choices=ItemType.choices)
    service = models.ForeignKey("services.Service", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    part = models.ForeignKey("inventory.Part", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    description = models.CharField(max_length=300)
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("1"),
                                   validators=[MinValueValidator(Decimal("0.01"))])
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"),
                                   validators=[MinValueValidator(Decimal("0"))])
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("18.00"))
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))

    class Meta:
        ordering = ("created_at",)
