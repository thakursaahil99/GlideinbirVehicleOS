"""
Channel providers. Business code never talks to a provider directly — it calls
NotificationService, and the Celery worker resolves the provider for the
channel from ``settings.NOTIFICATION_PROVIDERS``. Swap the dotted path to plug in
a real SMS / WhatsApp gateway; no business logic changes.
"""
import logging
import uuid
from dataclasses import dataclass

from django.conf import settings
from django.core.mail import send_mail
from django.utils.module_loading import import_string

logger = logging.getLogger("apps.notifications")


@dataclass
class DeliveryResult:
    ok: bool
    message_id: str = ""
    error: str = ""


class NotificationProvider:
    channel = ""

    def send(self, notification) -> DeliveryResult:  # pragma: no cover - interface
        raise NotImplementedError


class EmailProvider(NotificationProvider):
    """Uses Django's e-mail backend (console in development, SMTP/API in production)."""

    channel = "EMAIL"

    def send(self, notification):
        body = f"{notification.body}\n\n— Glideinbir\nBuilt by Sahil Thakur"
        send_mail(notification.title, body, settings.DEFAULT_FROM_EMAIL, [notification.to_address])
        return DeliveryResult(ok=True, message_id=f"email-{uuid.uuid4().hex[:12]}")


class MockSMSProvider(NotificationProvider):
    """Development stand-in: logs the SMS instead of sending it."""

    channel = "SMS"

    def send(self, notification):
        logger.info("[MOCK SMS] to=%s | %s", notification.to_address, notification.body[:300])
        return DeliveryResult(ok=True, message_id=f"mock-sms-{uuid.uuid4().hex[:12]}")


class MockWhatsAppProvider(NotificationProvider):
    channel = "WHATSAPP"

    def send(self, notification):
        logger.info("[MOCK WHATSAPP] to=%s | %s: %s", notification.to_address, notification.title,
                    notification.body[:300])
        return DeliveryResult(ok=True, message_id=f"mock-wa-{uuid.uuid4().hex[:12]}")


_cache = {}


def get_provider(channel) -> NotificationProvider:
    if channel not in _cache:
        path = settings.NOTIFICATION_PROVIDERS[channel]
        _cache[channel] = import_string(path)()
    return _cache[channel]


def reset_provider_cache():
    _cache.clear()
