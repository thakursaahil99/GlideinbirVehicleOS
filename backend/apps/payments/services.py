"""
PaymentService — every money movement goes through here and is audited.

* Customers pay online (MOCK / CARD / UPI) through the gateway provider.
* Agencies record offline receipts (CASH / BANK_TRANSFER).
* Refunds go back through the provider that took the money.
"""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.accounts.constants import StaffPermission
from apps.audit_logs.models import AuditAction
from apps.audit_logs.services import AuditService
from apps.bookings.models import Booking, PaymentStatus
from apps.core.exceptions import BusinessRuleViolation, InvalidStateTransition
from apps.core.tenancy import get_user_membership
from apps.invoices.models import Invoice, InvoiceStatus
from apps.invoices.services import InvoiceService, q

from .models import OFFLINE_METHODS, ONLINE_METHODS, Payment, PaymentRecordStatus
from .providers import get_gateway, get_offline

P = PaymentRecordStatus


def _require_agency(actor, organization_id, code=StaffPermission.PAYMENT_VIEW, admin_only=False):
    if actor.is_super_admin:
        return
    membership = get_user_membership(actor)
    if membership is None or membership.organization_id != organization_id:
        raise BusinessRuleViolation("Not found.", code="NOT_FOUND", status_code=404)
    if admin_only and actor.role != "AGENCY_ADMIN":
        raise BusinessRuleViolation("Only the agency admin can do this.", code="PERMISSION_DENIED", status_code=403)
    if not membership.has_permission(code):
        raise BusinessRuleViolation("You do not have permission for payments.", code="PERMISSION_DENIED",
                                    status_code=403)


def booking_total(booking):
    return q(booking.quoted_price + booking.quoted_price * booking.tax_rate / 100)


def _refresh(payment):
    if payment.invoice_id:
        InvoiceService.refresh_payment_status(Invoice.objects.get(pk=payment.invoice_id))
    elif payment.booking_id:
        paid = sum((p.net_amount for p in Payment.objects.filter(booking_id=payment.booking_id)), Decimal("0"))
        booking = Booking.objects.get(pk=payment.booking_id)
        total = booking_total(booking)
        status = (PaymentStatus.PAID if paid >= total else PaymentStatus.PARTIALLY_PAID if paid > 0
                  else PaymentStatus.REFUNDED if payment.refunded_amount else PaymentStatus.UNPAID)
        Booking.objects.filter(pk=booking.pk).update(payment_status=status)


class PaymentService:
    @staticmethod
    def create_booking_payment(booking):
        """Pending prepayment created with the booking when the agency requires online payment."""
        return Payment.objects.create(organization=booking.organization, booking=booking, customer=booking.customer,
                                      amount=booking_total(booking), method="MOCK", status=P.PENDING,
                                      created_by=booking.created_by)

    @staticmethod
    def _charge(payment, method, metadata, actor, request):
        provider = get_gateway() if method in ONLINE_METHODS else get_offline()
        result = provider.charge(amount=payment.amount, currency=payment.currency, method=method,
                                 reference=payment.reference, metadata=metadata)
        payment.method, payment.gateway = method, provider.name
        if result.success:
            payment.status, payment.transaction_id, payment.paid_at = P.SUCCEEDED, result.transaction_id, timezone.now()
            payment.failure_reason = ""
        else:
            payment.status, payment.failure_reason = P.FAILED, result.failure_reason[:300]
        payment.save()
        _refresh(payment)
        AuditService.log(AuditAction.PAYMENT_CHANGED, user=actor, organization=payment.organization,
                         instance=payment, request=request,
                         new_data={"status": payment.status, "amount": str(payment.amount), "method": method,
                                   "transaction_id": payment.transaction_id})
        if result.success:
            from apps.notifications.tasks import send_payment_notification

            pid = str(payment.pk)
            transaction.on_commit(lambda: send_payment_notification.delay(pid))
        return payment

    @staticmethod
    @transaction.atomic
    def pay_online(*, actor, method, invoice_id=None, payment_id=None, simulate=None, idempotency_key=None,
                   request=None):
        """Customer pays an invoice balance or a pending booking prepayment through the gateway."""
        if method not in ONLINE_METHODS:
            raise BusinessRuleViolation("Choose an online payment method.", code="INVALID_METHOD")
        if idempotency_key:
            previous = Payment.objects.filter(idempotency_key=idempotency_key).first()
            if previous:
                if previous.customer.user_id != actor.pk:
                    raise BusinessRuleViolation("Idempotency key already used.", code="IDEMPOTENCY_CONFLICT")
                return previous  # safe retry — never charge twice
        if payment_id:
            payment = Payment.objects.select_for_update().filter(pk=payment_id, customer__user=actor).first()
            if payment is None:
                raise BusinessRuleViolation("Payment not found.", code="NOT_FOUND", status_code=404)
            if payment.status not in (P.PENDING, P.FAILED):
                raise InvalidStateTransition("This payment is already settled.")
            payment.idempotency_key = idempotency_key or payment.idempotency_key
        else:
            invoice = Invoice.objects.select_for_update().filter(pk=invoice_id, customer__user=actor).first()
            if invoice is None:
                raise BusinessRuleViolation("Invoice not found.", code="NOT_FOUND", status_code=404)
            if invoice.status != InvoiceStatus.ISSUED or invoice.balance_due <= 0:
                raise BusinessRuleViolation("Nothing to pay on this invoice.", code="NOTHING_DUE")
            payment = Payment(organization=invoice.organization, invoice=invoice, booking=invoice.booking,
                              customer=invoice.customer, amount=invoice.balance_due, created_by=actor,
                              idempotency_key=idempotency_key)
        return PaymentService._charge(payment, method, {"simulate": simulate} if simulate else {}, actor, request)

    @staticmethod
    @transaction.atomic
    def record_offline(*, actor, invoice_id, amount, method, reference="", request=None):
        if method not in OFFLINE_METHODS:
            raise BusinessRuleViolation("Offline payments are CASH or BANK_TRANSFER.", code="INVALID_METHOD")
        invoice = Invoice.objects.select_for_update().filter(pk=invoice_id).first()
        if invoice is None:
            raise BusinessRuleViolation("Invoice not found.", code="NOT_FOUND", status_code=404)
        _require_agency(actor, invoice.organization_id, StaffPermission.PAYMENT_VIEW)
        amount = q(amount)
        if invoice.status != InvoiceStatus.ISSUED:
            raise BusinessRuleViolation("Payments can only be recorded on issued invoices.", code="INVOICE_NOT_ISSUED")
        if amount <= 0 or amount > invoice.balance_due:
            raise BusinessRuleViolation(f"Amount must be between 0.01 and {invoice.balance_due}.",
                                        code="INVALID_AMOUNT")
        payment = Payment(organization=invoice.organization, invoice=invoice, booking=invoice.booking,
                          customer=invoice.customer, amount=amount, reference=reference, created_by=actor)
        return PaymentService._charge(payment, method, {}, actor, request)

    @staticmethod
    @transaction.atomic
    def refund(*, actor, payment, amount=None, reason="", request=None):
        payment = Payment.objects.select_for_update().get(pk=payment.pk)
        _require_agency(actor, payment.organization_id, StaffPermission.PAYMENT_VIEW, admin_only=True)
        if payment.status not in (P.SUCCEEDED, P.PARTIALLY_REFUNDED):
            raise InvalidStateTransition("Only settled payments can be refunded.")
        refundable = payment.amount - payment.refunded_amount
        amount = q(amount) if amount is not None else refundable
        if amount <= 0 or amount > refundable:
            raise BusinessRuleViolation(f"You can refund up to {refundable}.", code="INVALID_AMOUNT")
        if not reason.strip():
            raise BusinessRuleViolation("A refund reason is required.", code="REASON_REQUIRED")
        provider = get_gateway() if payment.method in ONLINE_METHODS else get_offline()
        result = provider.refund(transaction_id=payment.transaction_id, amount=amount, currency=payment.currency)
        if not result.success:
            raise BusinessRuleViolation(f"Refund failed: {result.failure_reason}", code="REFUND_FAILED")
        old = {"status": payment.status, "refunded_amount": str(payment.refunded_amount)}
        payment.refunded_amount += amount
        payment.status = P.REFUNDED if payment.refunded_amount >= payment.amount else P.PARTIALLY_REFUNDED
        payment.save(update_fields=["refunded_amount", "status", "updated_at"])
        _refresh(payment)
        AuditService.log(AuditAction.PAYMENT_REFUNDED, user=actor, organization=payment.organization,
                         instance=payment, request=request, old_data=old,
                         new_data={"status": payment.status, "refunded_amount": str(payment.refunded_amount),
                                   "refund_id": result.refund_id, "reason": reason.strip()})
        return payment

    @staticmethod
    def notify_received(payment_id):
        from apps.notifications.models import Event
        from apps.notifications.services import NotificationService

        payment = Payment.objects.select_related("customer__user", "invoice", "booking", "organization").filter(
            pk=payment_id).first()
        if payment is None:
            return
        reference = (payment.invoice.invoice_number if payment.invoice_id
                     else payment.booking.booking_number if payment.booking_id else "your service")
        customer = payment.customer
        NotificationService.notify(
            Event.PAYMENT_RECEIVED, users=[customer.user] if customer.user_id else [],
            contacts=[] if customer.user_id else [(customer.email, customer.phone)],
            organization=payment.organization,
            context={"amount": f"{payment.amount:,.2f}", "reference": reference},
            data={"payment_id": str(payment.pk)},
        )
