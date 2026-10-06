"""
InvoiceService — builds invoices from bookings, keeps totals exact (Decimal,
ROUND_HALF_UP per line), tracks payments, and renders/stores PDFs.
"""
from decimal import ROUND_HALF_UP, Decimal

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from apps.audit_logs.models import AuditAction
from apps.audit_logs.services import AuditService
from apps.bookings.models import Booking, PaymentStatus
from apps.core.exceptions import BusinessRuleViolation, InvalidStateTransition
from apps.core.numbering import next_number
from apps.job_cards.models import AdditionalWorkStatus

from .models import Invoice, InvoiceItem, InvoiceStatus, ItemType

CENT = Decimal("0.01")


def q(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def compute_line(quantity, unit_price, tax_rate, discount=Decimal("0")):
    base = q(Decimal(quantity) * Decimal(unit_price)) - q(discount)
    base = max(base, Decimal("0"))
    tax = q(base * Decimal(tax_rate) / 100)
    return base, tax, base + tax


class InvoiceService:
    @staticmethod
    def _add_item(invoice, **kw):
        base, tax, total = compute_line(kw.get("quantity", 1), kw["unit_price"], kw.get("tax_rate", 0),
                                        kw.get("discount", Decimal("0")))
        return InvoiceItem.objects.create(invoice=invoice, tax_amount=tax, total=total, **kw)

    @staticmethod
    def recalculate(invoice):
        subtotal = tax = Decimal("0")
        for item in invoice.items.all():
            base, item_tax, total = compute_line(item.quantity, item.unit_price, item.tax_rate, item.discount)
            if (item.tax_amount, item.total) != (item_tax, total):
                item.tax_amount, item.total = item_tax, total
                item.save(update_fields=["tax_amount", "total", "updated_at"])
            subtotal += base
            tax += item_tax
        discount = min(q(invoice.discount), subtotal)
        # Invoice-level discount reduces taxable value proportionally.
        if discount and subtotal:
            tax = q(tax * (subtotal - discount) / subtotal)
        invoice.subtotal, invoice.discount, invoice.tax = q(subtotal), discount, q(tax)
        invoice.total = q(subtotal - discount + tax)
        InvoiceService.refresh_payment_status(invoice, save=False)
        invoice.save()
        return invoice

    @staticmethod
    def refresh_payment_status(invoice, save=True):
        from apps.payments.models import Payment

        paid = sum((p.net_amount for p in Payment.objects.filter(invoice=invoice)), Decimal("0"))
        refunded_any = Payment.objects.filter(invoice=invoice, refunded_amount__gt=0).exists()
        invoice.amount_paid = q(paid)
        if invoice.total > 0 and paid >= invoice.total:
            status = PaymentStatus.PAID
        elif paid > 0:
            status = PaymentStatus.PARTIALLY_PAID
        elif refunded_any:
            status = PaymentStatus.REFUNDED
        else:
            status = PaymentStatus.UNPAID if invoice.total > 0 else PaymentStatus.PAID
        invoice.payment_status = status
        if save:
            invoice.save(update_fields=["amount_paid", "payment_status", "updated_at"])
        if invoice.booking_id:
            Booking.objects.filter(pk=invoice.booking_id).update(payment_status=status)
        return invoice

    @staticmethod
    @transaction.atomic
    def generate_for_booking(booking, actor=None, notify=True):
        """Idempotent: one invoice per booking with the service, approved extra work and parts used."""
        booking = Booking.objects.select_for_update().select_related(
            "vendor_service__service", "customer", "organization").get(pk=booking.pk)
        existing = Invoice.objects.filter(booking=booking).first()
        if existing:
            return existing
        now = timezone.now()
        invoice = Invoice.objects.create(
            organization=booking.organization, customer=booking.customer, booking=booking,
            invoice_number=next_number("INV"), invoice_date=timezone.localdate(), due_date=timezone.localdate(),
            status=InvoiceStatus.ISSUED, issued_at=now, created_by=actor,
        )
        service = booking.vendor_service.service
        InvoiceService._add_item(invoice, item_type=ItemType.SERVICE, service=service, description=service.name,
                                 quantity=Decimal("1"), unit_price=booking.quoted_price, tax_rate=booking.tax_rate)
        job_card = getattr(booking, "job_card", None)
        if job_card is not None:
            for req in job_card.additional_work.filter(status=AdditionalWorkStatus.APPROVED):
                InvoiceService._add_item(invoice, item_type=ItemType.ADDITIONAL_WORK,
                                         description=f"Additional work: {req.description[:250]}",
                                         quantity=Decimal("1"), unit_price=req.estimated_cost,
                                         tax_rate=booking.tax_rate)
            for usage in job_card.parts_used.select_related("part"):
                if usage.net_quantity > 0:
                    InvoiceService._add_item(invoice, item_type=ItemType.PART, part=usage.part,
                                             description=f"{usage.part.name} ({usage.part.sku})",
                                             quantity=usage.net_quantity, unit_price=usage.unit_price,
                                             tax_rate=usage.tax_rate)
        # Attach any prepayment made at booking time.
        from apps.payments.models import Payment

        Payment.objects.filter(booking=booking, invoice__isnull=True).update(invoice=invoice)
        InvoiceService.recalculate(invoice)
        AuditService.log(AuditAction.INVOICE_CHANGED, user=actor, organization=invoice.organization,
                         instance=invoice, new_data={"invoice_number": invoice.invoice_number,
                                                     "total": str(invoice.total), "generated": True})
        if notify:
            transaction.on_commit(lambda: _after_issue(invoice.pk))
        return invoice

    @staticmethod
    def generate_for_booking_async(booking_id):
        from .tasks import generate_invoice

        generate_invoice.delay(str(booking_id))

    @staticmethod
    def render_pdf(invoice):
        from .pdf import render_invoice_pdf

        invoice = Invoice.objects.select_related("organization", "customer", "booking__vehicle").get(pk=invoice.pk)
        content = render_invoice_pdf(invoice)
        if invoice.pdf:
            invoice.pdf.delete(save=False)
        invoice.pdf.save(f"{invoice.invoice_number}.pdf", ContentFile(content), save=False)
        Invoice.objects.filter(pk=invoice.pk).update(pdf=invoice.pdf.name)
        return invoice

    @staticmethod
    @transaction.atomic
    def update(*, invoice, actor, discount=None, notes=None, request=None):
        invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
        if invoice.status == InvoiceStatus.VOID:
            raise BusinessRuleViolation("Void invoices can't be changed.", code="INVOICE_VOID")
        old = {"discount": str(invoice.discount), "notes": invoice.notes}
        if discount is not None:
            if invoice.amount_paid > 0:
                raise BusinessRuleViolation("Discounts can't change after a payment was received.",
                                            code="INVOICE_HAS_PAYMENTS")
            invoice.discount = q(discount)
        if notes is not None:
            invoice.notes = notes
        InvoiceService.recalculate(invoice)
        AuditService.log(AuditAction.INVOICE_CHANGED, user=actor, organization=invoice.organization,
                         instance=invoice, request=request, old_data=old,
                         new_data={"discount": str(invoice.discount), "notes": invoice.notes,
                                   "total": str(invoice.total)})
        transaction.on_commit(lambda: InvoiceService.render_pdf(invoice))
        return invoice

    @staticmethod
    @transaction.atomic
    def void(*, invoice, actor, reason, request=None):
        invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
        if invoice.status == InvoiceStatus.VOID:
            raise InvalidStateTransition("Invoice is already void.")
        if invoice.amount_paid > 0:
            raise BusinessRuleViolation("Refund payments before voiding this invoice.", code="INVOICE_HAS_PAYMENTS")
        if not reason.strip():
            raise BusinessRuleViolation("A reason is required.", code="REASON_REQUIRED")
        invoice.status, invoice.voided_at, invoice.void_reason = InvoiceStatus.VOID, timezone.now(), reason.strip()
        invoice.save(update_fields=["status", "voided_at", "void_reason", "updated_at"])
        AuditService.log(AuditAction.INVOICE_VOIDED, user=actor, organization=invoice.organization,
                         instance=invoice, request=request, new_data={"reason": reason.strip()})
        return invoice

    @staticmethod
    def notify_generated(invoice_id):
        from apps.notifications.models import Event
        from apps.notifications.services import NotificationService

        invoice = Invoice.objects.select_related("customer__user", "organization").filter(pk=invoice_id).first()
        if invoice is None:
            return
        customer = invoice.customer
        NotificationService.notify(
            Event.INVOICE_GENERATED, users=[customer.user] if customer.user_id else [],
            contacts=[] if customer.user_id else [(customer.email, customer.phone)],
            organization=invoice.organization,
            context={"invoice_number": invoice.invoice_number, "amount": f"{invoice.total:,.2f}"},
            data={"invoice_id": str(invoice.pk)},
        )


def _after_issue(invoice_id):
    from apps.notifications.tasks import send_invoice_email

    invoice = Invoice.objects.get(pk=invoice_id)
    InvoiceService.render_pdf(invoice)
    send_invoice_email.delay(str(invoice_id))
