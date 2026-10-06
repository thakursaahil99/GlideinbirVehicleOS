from django.conf import settings
from django.db import models

from apps.core.models import BaseModel


class Channel(models.TextChoices):
    IN_APP = "IN_APP", "In-app"
    EMAIL = "EMAIL", "E-mail"
    SMS = "SMS", "SMS"
    WHATSAPP = "WHATSAPP", "WhatsApp"


class Event(models.TextChoices):
    BOOKING_CREATED = "BOOKING_CREATED", "Booking created"
    BOOKING_CONFIRMED = "BOOKING_CONFIRMED", "Booking confirmed"
    BOOKING_REJECTED = "BOOKING_REJECTED", "Booking rejected"
    BOOKING_CANCELLED = "BOOKING_CANCELLED", "Booking cancelled"
    BOOKING_RESCHEDULED = "BOOKING_RESCHEDULED", "Booking rescheduled"
    BOOKING_REMINDER = "BOOKING_REMINDER", "Booking reminder"
    VEHICLE_RECEIVED = "VEHICLE_RECEIVED", "Vehicle received"
    SERVICE_STARTED = "SERVICE_STARTED", "Service started"
    ADDITIONAL_WORK_REQUESTED = "ADDITIONAL_WORK_REQUESTED", "Additional work requested"
    ADDITIONAL_WORK_RESPONDED = "ADDITIONAL_WORK_RESPONDED", "Additional work responded"
    SERVICE_COMPLETED = "SERVICE_COMPLETED", "Service completed"
    PAYMENT_RECEIVED = "PAYMENT_RECEIVED", "Payment received"
    INVOICE_GENERATED = "INVOICE_GENERATED", "Invoice generated"
    NEW_BOOKING_FOR_AGENCY = "NEW_BOOKING_FOR_AGENCY", "New booking (agency)"


class DeliveryStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    SENT = "SENT", "Sent"
    FAILED = "FAILED", "Failed"
    SKIPPED = "SKIPPED", "Skipped"


class Notification(BaseModel):
    """
    One message on one channel. ``recipient`` is set for platform users;
    walk-in customers without an account are reached via ``to_address`` only.
    """

    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE,
                                  related_name="notifications")
    organization = models.ForeignKey("organizations.Organization", null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name="+")
    event = models.CharField(max_length=32, choices=Event.choices)
    channel = models.CharField(max_length=10, choices=Channel.choices)
    to_address = models.CharField(max_length=254, blank=True, help_text="E-mail or phone for external channels")
    title = models.CharField(max_length=200)
    body = models.TextField()
    data = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=10, choices=DeliveryStatus.choices, default=DeliveryStatus.PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    error = models.CharField(max_length=500, blank=True)
    provider_message_id = models.CharField(max_length=100, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["recipient", "channel", "-created_at"], name="notification_inbox_idx"),
            models.Index(fields=["recipient", "read_at"], name="notification_unread_idx"),
            models.Index(fields=["status", "channel"], name="notification_delivery_idx"),
        ]

    def __str__(self):
        return f"{self.event} → {self.recipient or self.to_address} ({self.channel})"
