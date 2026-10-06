from celery import shared_task


@shared_task(autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def generate_invoice(booking_id):
    from apps.bookings.models import Booking

    from .services import InvoiceService

    booking = Booking.objects.filter(pk=booking_id).first()
    if booking is not None:
        InvoiceService.generate_for_booking(booking)


@shared_task(autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def render_invoice_pdf(invoice_id):
    from .models import Invoice
    from .services import InvoiceService

    invoice = Invoice.objects.filter(pk=invoice_id).first()
    if invoice is not None:
        InvoiceService.render_pdf(invoice)
