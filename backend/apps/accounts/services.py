"""Authentication business logic. Views stay thin and call into AuthService / UserService."""
from django.contrib.auth import authenticate, password_validation
from django.contrib.auth.models import update_last_login
from django.db import transaction
from django.utils import timezone
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit_logs.models import AuditAction
from apps.audit_logs.services import AuditService
from apps.core.exceptions import AppError, BusinessRuleViolation, InvalidCredentials, InvalidToken
from apps.core.tenancy import get_user_membership, get_user_organization

from . import tasks
from .constants import Role
from .models import User
from .tokens import decode_uid, email_verification_token, password_reset_token


def _user_from_uid(uidb64):
    pk = decode_uid(uidb64)
    if not pk:
        return None
    try:
        return User.objects.filter(pk=pk).first()
    except (ValueError, TypeError):  # malformed UUID
        return None


class AuthService:
    @staticmethod
    def issue_tokens(user):
        """
        Create a refresh/access pair. The ``role`` and ``organization_id`` claims
        are informational for the UI only — the backend never trusts them for
        authorization.
        """
        refresh = RefreshToken.for_user(user)
        refresh["role"] = user.role
        membership = get_user_membership(user)
        refresh["organization_id"] = str(membership.organization_id) if membership else None
        return {"access": str(refresh.access_token), "refresh": str(refresh)}

    @staticmethod
    @transaction.atomic
    def register_customer(*, email, password, full_name, phone="", request=None):
        user = User.objects.create_user(
            email=email, password=password, full_name=full_name, phone=phone, role=Role.CUSTOMER
        )
        from apps.customers.services import CustomerService

        CustomerService.ensure_profile(user)
        AuditService.log(AuditAction.USER_CREATED, user=user, instance=user, request=request,
                         new_data={"email": user.email, "role": user.role, "self_registered": True})
        transaction.on_commit(lambda: tasks.send_verification_email.delay(str(user.pk)))
        return user

    @staticmethod
    def login(*, email, password, request=None):
        user = authenticate(request=request, email=email.strip().lower(), password=password)
        if user is None:
            # ModelBackend returns None for wrong passwords AND inactive users; don't reveal which.
            known = User.objects.filter(email__iexact=email.strip()).first()
            AuditService.log(AuditAction.LOGIN_FAILED, user=known, request=request,
                             model_name="User", object_id=str(known.pk) if known else "",
                             new_data={"email": email.strip().lower()[:254]})
            raise InvalidCredentials()
        update_last_login(None, user)
        AuditService.log(AuditAction.LOGIN, user=user, organization=get_user_organization(user),
                         instance=user, request=request)
        return user, AuthService.issue_tokens(user)

    @staticmethod
    def logout(*, user, refresh_token, request=None):
        try:
            token = RefreshToken(refresh_token)
        except TokenError as exc:
            raise InvalidToken("Refresh token is invalid or expired.", code="TOKEN_INVALID") from exc
        if str(token.get("user_id")) != str(user.pk):
            raise InvalidToken("Refresh token does not belong to this user.", code="TOKEN_INVALID")
        token.blacklist()
        AuditService.log(AuditAction.LOGOUT, user=user, organization=get_user_organization(user),
                         instance=user, request=request)

    @staticmethod
    def revoke_all_refresh_tokens(user):
        for outstanding in OutstandingToken.objects.filter(user=user, expires_at__gt=timezone.now()):
            BlacklistedToken.objects.get_or_create(token=outstanding)

    @staticmethod
    @transaction.atomic
    def change_password(*, user, current_password, new_password, request=None):
        if not user.check_password(current_password):
            raise AppError("Current password is incorrect.", code="INVALID_PASSWORD")
        password_validation.validate_password(new_password, user)
        user.set_password(new_password)
        user.save(update_fields=["password", "updated_at"])
        AuthService.revoke_all_refresh_tokens(user)
        AuditService.log(AuditAction.PASSWORD_CHANGED, user=user, organization=get_user_organization(user),
                         instance=user, request=request)

    @staticmethod
    def request_password_reset(*, email, request=None):
        """Always succeeds from the caller's point of view to prevent account enumeration."""
        user = User.objects.filter(email__iexact=email.strip(), is_active=True).first()
        if user is None:
            return
        AuditService.log(AuditAction.PASSWORD_RESET_REQUESTED, user=user, instance=user, request=request)
        transaction.on_commit(lambda: tasks.send_password_reset_email.delay(str(user.pk)))

    @staticmethod
    @transaction.atomic
    def confirm_password_reset(*, uid, token, new_password, request=None):
        user = _user_from_uid(uid)
        if user is None or not user.is_active or not password_reset_token.check_token(user, token):
            raise InvalidToken()
        password_validation.validate_password(new_password, user)
        user.set_password(new_password)  # changing the hash invalidates the reset token
        user.save(update_fields=["password", "updated_at"])
        AuthService.revoke_all_refresh_tokens(user)
        AuditService.log(AuditAction.PASSWORD_RESET, user=user, instance=user, request=request)

    @staticmethod
    def send_verification(user):
        if user.email_verified:
            raise BusinessRuleViolation("E-mail is already verified.", code="EMAIL_ALREADY_VERIFIED")
        transaction.on_commit(lambda: tasks.send_verification_email.delay(str(user.pk)))

    @staticmethod
    @transaction.atomic
    def verify_email(*, uid, token, request=None):
        user = _user_from_uid(uid)
        if user is None or not email_verification_token.check_token(user, token):
            raise InvalidToken()
        user.email_verified = True
        user.email_verified_at = timezone.now()
        user.save(update_fields=["email_verified", "email_verified_at", "updated_at"])
        AuditService.log(AuditAction.EMAIL_VERIFIED, user=user, instance=user, request=request)
        return user


class UserService:
    @staticmethod
    @transaction.atomic
    def set_active(*, target, active, actor, request=None):
        if target.pk == actor.pk:
            raise BusinessRuleViolation("You cannot change the active state of your own account.",
                                        code="CANNOT_MODIFY_SELF")
        if target.is_active == active:
            return target
        target.is_active = active
        target.save(update_fields=["is_active", "updated_at"])
        if not active:
            AuthService.revoke_all_refresh_tokens(target)
        AuditService.log(
            AuditAction.USER_ACTIVATED if active else AuditAction.USER_DEACTIVATED,
            user=actor, organization=get_user_organization(target), instance=target, request=request,
            old_data={"is_active": not active}, new_data={"is_active": active},
        )
        return target

    @staticmethod
    @transaction.atomic
    def update_profile(*, user, data, request=None):
        fields = [f for f in ("full_name", "phone", "profile_photo") if f in data]
        old = {f: str(getattr(user, f)) for f in fields}
        for field in fields:
            setattr(user, field, data[field])
        if fields:
            user.save(update_fields=[*fields, "updated_at"])
            if user.is_customer:
                from apps.customers.services import CustomerService

                CustomerService.sync_from_user(user)
            AuditService.log(AuditAction.USER_UPDATED, user=user, organization=get_user_organization(user),
                             instance=user, request=request, old_data=old,
                             new_data={f: str(getattr(user, f)) for f in fields})
        return user
