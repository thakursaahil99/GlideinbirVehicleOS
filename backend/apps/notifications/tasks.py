"""Celery tasks: channel delivery plus the scheduled/named notification jobs."""
import logging
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from .models import Notification

logger = logging.getLogger(__name__)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=600, max_retries=5)
def deliver_notification(self, notification_id):
    from .services import NotificationService

    notification = Notification.objects.filter(pk=notification_id).first()
    if notification is None:
        return
    NotificationService.deliver(notification)


@shared_task
def send_booking_confirmation(booking_id):
    from apps.bookings import events
    from apps.bookings.models import Booking

    booking = Booking.objects.select_related("customer__user", "vehicle", "vendor_service__service",
                                             "organization").filter(pk=booking_id).first()
    if booking:
        events.notify_customer(booking, "BOOKING_CONFIRMED")


@shared_task
def send_booking_reminder(hours_ahead=24):
    """Celery Beat: remind customers about bookings starting within ``hours_ahead`` hours (once each)."""
    from apps.bookings import events
    from apps.bookings.models import ACTIVE_STATUSES, Booking

    now = timezone.now()
    due = (Booking.objects.filter(status__in=ACTIVE_STATUSES, reminder_sent_at__isnull=True,
                                  start_datetime__gt=now, start_datetime__lte=now + timedelta(hours=hours_ahead))
           .select_related("customer__user", "vehicle", "vendor_service__service", "organization"))
    sent = 0
    for booking in due.iterator():
        with transaction.atomic():
            # Claim the row so overlapping beat runs never double-send.
            claimed = Booking.objects.filter(pk=booking.pk, reminder_sent_at__isnull=True).update(reminder_sent_at=now)
            if claimed:
                events.notify_customer(booking, "BOOKING_REMINDER")
                sent += 1
    logger.info("Booking reminders sent: %s", sent)
    return sent


@shared_task
def send_invoice_email(invoice_id):
    from apps.invoices.services import InvoiceService

    InvoiceService.notify_generated(invoice_id)


@shared_task
def send_payment_notification(payment_id):
    from apps.payments.services import PaymentService

    PaymentService.notify_received(payment_id)
