from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import TenantModel
from apps.core.tenancy import TenantQuerySet


class PaymentMethod(models.TextChoices):
    MOCK = "MOCK", "Mock gateway"
    CASH = "CASH", "Cash"
    BANK_TRANSFER = "BANK_TRANSFER", "Bank transfer"
    CARD = "CARD", "Card"
    UPI = "UPI", "UPI"


ONLINE_METHODS = {PaymentMethod.MOCK, PaymentMethod.CARD, PaymentMethod.UPI}
OFFLINE_METHODS = {PaymentMethod.CASH, PaymentMethod.BANK_TRANSFER}


class PaymentRecordStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    SUCCEEDED = "SUCCEEDED", "Succeeded"
    FAILED = "FAILED", "Failed"
    REFUNDED = "REFUNDED", "Refunded"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED", "Partially refunded"


class PaymentQuerySet(TenantQuerySet):
    def for_user(self, user):
        if user is not None and getattr(user, "is_authenticated", False) and user.is_customer:
            return self.filter(customer__user=user)
        return super().for_user(user)

    def settled(self):
        return self.filter(status__in=[PaymentRecordStatus.SUCCEEDED, PaymentRecordStatus.PARTIALLY_REFUNDED,
                                       PaymentRecordStatus.REFUNDED])


class Payment(TenantModel):
    booking = models.ForeignKey("bookings.Booking", null=True, blank=True, on_delete=models.PROTECT,
                                related_name="payments")
    invoice = models.ForeignKey("invoices.Invoice", null=True, blank=True, on_delete=models.PROTECT,
                                related_name="payments")
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    refunded_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    currency = models.CharField(max_length=3, default="INR")
    method = models.CharField(max_length=16, choices=PaymentMethod.choices, default=PaymentMethod.MOCK)
    status = models.CharField(max_length=20, choices=PaymentRecordStatus.choices, default=PaymentRecordStatus.PENDING)
    gateway = models.CharField(max_length=40, blank=True)
    transaction_id = models.CharField(max_length=100, blank=True, db_index=True)
    reference = models.CharField(max_length=100, blank=True, help_text="Cheque / UTR / receipt number")
    failure_reason = models.CharField(max_length=300, blank=True)
    idempotency_key = models.CharField(max_length=64, null=True, blank=True, unique=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")

    objects = PaymentQuerySet.as_manager()

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["organization", "status", "-created_at"], name="payment_org_status_idx"),
            models.Index(fields=["booking"], name="payment_booking_idx"),
            models.Index(fields=["invoice"], name="payment_invoice_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="payment_amount_positive"),
            models.CheckConstraint(condition=models.Q(refunded_amount__gte=0)
                                   & models.Q(refunded_amount__lte=models.F("amount")),
                                   name="payment_refund_within_amount"),
        ]

    def __str__(self):
        return f"{self.method} {self.amount} {self.status}"

    @property
    def net_amount(self):
        if self.status in (PaymentRecordStatus.SUCCEEDED, PaymentRecordStatus.PARTIALLY_REFUNDED,
                           PaymentRecordStatus.REFUNDED):
            return self.amount - self.refunded_amount
        return Decimal("0")
