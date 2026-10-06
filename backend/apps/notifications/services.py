"""
NotificationService — one call fans an event out to IN_APP (stored immediately)
and EMAIL / SMS / WHATSAPP (delivered asynchronously by Celery through the
configured providers).
"""
from django.db import transaction
from django.utils import timezone

from .models import Channel, DeliveryStatus, Event, Notification

# Which external channels each event uses (IN_APP is always on for platform users).
EVENT_CHANNELS = {
    Event.BOOKING_CREATED: (Channel.EMAIL, Channel.SMS),
    Event.BOOKING_CONFIRMED: (Channel.EMAIL, Channel.SMS, Channel.WHATSAPP),
    Event.BOOKING_REJECTED: (Channel.EMAIL, Channel.SMS),
    Event.BOOKING_CANCELLED: (Channel.EMAIL, Channel.SMS),
    Event.BOOKING_RESCHEDULED: (Channel.EMAIL, Channel.SMS, Channel.WHATSAPP),
    Event.BOOKING_REMINDER: (Channel.SMS, Channel.WHATSAPP),
    Event.VEHICLE_RECEIVED: (Channel.SMS,),
    Event.SERVICE_STARTED: (Channel.SMS,),
    Event.ADDITIONAL_WORK_REQUESTED: (Channel.EMAIL, Channel.SMS, Channel.WHATSAPP),
    Event.ADDITIONAL_WORK_RESPONDED: (),
    Event.SERVICE_COMPLETED: (Channel.EMAIL, Channel.SMS, Channel.WHATSAPP),
    Event.PAYMENT_RECEIVED: (Channel.EMAIL, Channel.SMS),
    Event.INVOICE_GENERATED: (Channel.EMAIL,),
    Event.NEW_BOOKING_FOR_AGENCY: (Channel.EMAIL,),
}

TEMPLATES = {
    Event.BOOKING_CREATED: ("Booking {booking_number} received",
                            "We received your booking for {service} on {when} at {agency}. "
                            "You'll be notified once it's confirmed."),
    Event.BOOKING_CONFIRMED: ("Booking {booking_number} confirmed",
                              "{agency} confirmed your {service} on {when} for {vehicle}."),
    Event.BOOKING_REJECTED: ("Booking {booking_number} declined",
                             "{agency} couldn't accept your booking for {when}. {reason}"),
    Event.BOOKING_CANCELLED: ("Booking {booking_number} cancelled",
                              "Your booking for {service} on {when} was cancelled. Reason: {reason}"),
    Event.BOOKING_RESCHEDULED: ("Booking {booking_number} rescheduled",
                                "Your {service} at {agency} moved to {when}."),
    Event.BOOKING_REMINDER: ("Reminder: {service} {when}",
                             "Reminder: your {service} at {agency} is on {when} for {vehicle}."),
    Event.VEHICLE_RECEIVED: ("Vehicle received", "{agency} has received {vehicle} for booking {booking_number}."),
    Event.SERVICE_STARTED: ("Service started", "Work on {vehicle} has started ({booking_number})."),
    Event.ADDITIONAL_WORK_REQUESTED: ("Approval needed: additional work",
                                      "{agency} recommends: {description} (est. ₹{amount}). "
                                      "Please approve or decline in the app."),
    Event.ADDITIONAL_WORK_RESPONDED: ("Customer {decision} additional work",
                                      "{customer} {decision} '{description}' on {booking_number}."),
    Event.SERVICE_COMPLETED: ("Your vehicle is ready", "{vehicle} is ready for pickup at {agency} ({booking_number})."),
    Event.PAYMENT_RECEIVED: ("Payment received", "We received ₹{amount} for {reference}. Thank you!"),
    Event.INVOICE_GENERATED: ("Invoice {invoice_number}", "Your invoice {invoice_number} for ₹{amount} is ready."),
    Event.NEW_BOOKING_FOR_AGENCY: ("New booking {booking_number}",
                                   "{customer} booked {service} on {when} ({vehicle})."),
}


class _SafeDict(dict):
    def __missing__(self, key):
        return ""


def render(event, context):
    title, body = TEMPLATES[event]
    ctx = _SafeDict(context)
    return title.format_map(ctx)[:200], body.format_map(ctx)


class NotificationService:
    @staticmethod
    def notify(event, *, users=(), organization=None, context=None, data=None, contacts=(), channels=None):
        """
        ``users``    — platform users (get IN_APP + external channels at their e-mail/phone).
        ``contacts`` — (email, phone) pairs without an account (walk-ins): external channels only.
        Creates rows now; external deliveries are queued after the surrounding transaction commits.
        """
        context = context or {}
        data = data or {}
        title, body = render(event, context)
        external = channels if channels is not None else EVENT_CHANNELS.get(event, ())
        created = []

        def _add(**kw):
            created.append(Notification(event=event, organization=organization, title=title, body=body, data=data,
                                        **kw))

        seen = set()
        for user in users:
            if user is None or not user.is_active or user.pk in seen:
                continue
            seen.add(user.pk)
            _add(recipient=user, channel=Channel.IN_APP, status=DeliveryStatus.SENT, sent_at=timezone.now())
            for ch in external:
                address = user.email if ch == Channel.EMAIL else user.phone
                if address:
                    _add(recipient=user, channel=ch, to_address=address)
        for email, phone in contacts:
            for ch in external:
                address = email if ch == Channel.EMAIL else phone
                if address:
                    _add(channel=ch, to_address=address)

        rows = Notification.objects.bulk_create(created)
        pending = [str(n.pk) for n in rows if n.status == DeliveryStatus.PENDING]
        if pending:
            from .tasks import deliver_notification

            transaction.on_commit(lambda: [deliver_notification.delay(pk) for pk in pending])
        return rows

    @staticmethod
    def deliver(notification):
        from .providers import get_provider

        if notification.status == DeliveryStatus.SENT:
            return notification
        notification.attempts += 1
        try:
            result = get_provider(notification.channel).send(notification)
        except Exception as exc:  # noqa: BLE001 — provider failures are recorded, never raised to users
            notification.status, notification.error = DeliveryStatus.FAILED, str(exc)[:500]
            notification.save(update_fields=["status", "error", "attempts", "updated_at"])
            raise
        if result.ok:
            notification.status, notification.sent_at = DeliveryStatus.SENT, timezone.now()
            notification.provider_message_id, notification.error = result.message_id, ""
        else:
            notification.status, notification.error = DeliveryStatus.FAILED, result.error[:500]
        notification.save(update_fields=["status", "sent_at", "provider_message_id", "error", "attempts",
                                         "updated_at"])
        return notification

    @staticmethod
    def mark_read(user, ids=None):
        qs = Notification.objects.filter(recipient=user, channel=Channel.IN_APP, read_at__isnull=True)
        if ids is not None:
            qs = qs.filter(pk__in=ids)
        return qs.update(read_at=timezone.now())
