"""
Account e-mails. Tokens are generated inside the worker so no secret ever
travels through the Redis broker.
"""
import logging

from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.core.management import call_command

from .tokens import email_verification_token, encode_uid, password_reset_token

logger = logging.getLogger(__name__)

SIGNATURE = "\n\n— Vehicle Service CRM\nBuilt by Sahil Thakur"


def _get_active_user(user_id):
    return get_user_model().objects.filter(pk=user_id, is_active=True).first()


@shared_task(autoretry_for=(ConnectionError, TimeoutError), retry_backoff=True, max_retries=3)
def send_password_reset_email(user_id):
    user = _get_active_user(user_id)
    if user is None:
        return
    link = f"{settings.FRONTEND_URL}/reset-password?uid={encode_uid(user)}&token={password_reset_token.make_token(user)}"
    send_mail(
        subject="Reset your Vehicle Service CRM password",
        message=(
            f"Hi {user.full_name},\n\nUse the link below to set a new password. "
            f"It expires in {settings.PASSWORD_RESET_TIMEOUT // 3600} hours.\n\n{link}\n\n"
            "If you did not request this, you can ignore this e-mail." + SIGNATURE
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
    )


@shared_task(autoretry_for=(ConnectionError, TimeoutError), retry_backoff=True, max_retries=3)
def send_verification_email(user_id):
    user = _get_active_user(user_id)
    if user is None or user.email_verified:
        return
    link = f"{settings.FRONTEND_URL}/verify-email?uid={encode_uid(user)}&token={email_verification_token.make_token(user)}"
    send_mail(
        subject="Verify your Vehicle Service CRM e-mail",
        message=f"Hi {user.full_name},\n\nPlease confirm your e-mail address:\n\n{link}" + SIGNATURE,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
    )


@shared_task(autoretry_for=(ConnectionError, TimeoutError), retry_backoff=True, max_retries=3)
def send_staff_invite_email(user_id, organization_name):
    """Invite a new agency member to set their password (uses the password-reset token)."""
    user = _get_active_user(user_id)
    if user is None:
        return
    link = f"{settings.FRONTEND_URL}/reset-password?uid={encode_uid(user)}&token={password_reset_token.make_token(user)}"
    send_mail(
        subject=f"You've been invited to {organization_name} on Vehicle Service CRM",
        message=(
            f"Hi {user.full_name},\n\n{organization_name} has added you to their workshop team. "
            f"Set your password to get started:\n\n{link}\n\n"
            f"The link expires in {settings.PASSWORD_RESET_TIMEOUT // 3600} hours." + SIGNATURE
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
    )


@shared_task
def cleanup_expired_tokens():
    """Remove expired outstanding/blacklisted JWT refresh tokens."""
    call_command("flushexpiredtokens")
    logger.info("Expired JWT tokens flushed.")
