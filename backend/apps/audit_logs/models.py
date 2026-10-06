"""
Immutable audit trail.

Immutability is enforced twice: in the ORM (save/delete/update raise) and in
PostgreSQL by a trigger that rejects UPDATE and DELETE on the table.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import UUIDModel
from apps.core.tenancy import TenantQuerySet


class AuditAction(models.TextChoices):
    LOGIN = "LOGIN", "Login"
    LOGIN_FAILED = "LOGIN_FAILED", "Login failed"
    LOGOUT = "LOGOUT", "Logout"
    PASSWORD_CHANGED = "PASSWORD_CHANGED", "Password changed"
    PASSWORD_RESET_REQUESTED = "PASSWORD_RESET_REQUESTED", "Password reset requested"
    PASSWORD_RESET = "PASSWORD_RESET", "Password reset"
    EMAIL_VERIFIED = "EMAIL_VERIFIED", "Email verified"
    USER_CREATED = "USER_CREATED", "User created"
    USER_UPDATED = "USER_UPDATED", "User updated"
    USER_ACTIVATED = "USER_ACTIVATED", "User activated"
    USER_DEACTIVATED = "USER_DEACTIVATED", "User deactivated"
    PERMISSIONS_CHANGED = "PERMISSIONS_CHANGED", "Permissions changed"
    AGENCY_REGISTERED = "AGENCY_REGISTERED", "Agency registered"
    AGENCY_UPDATED = "AGENCY_UPDATED", "Agency updated"
    AGENCY_APPROVED = "AGENCY_APPROVED", "Agency approved"
    AGENCY_REJECTED = "AGENCY_REJECTED", "Agency rejected"
    AGENCY_SUSPENDED = "AGENCY_SUSPENDED", "Agency suspended"
    AGENCY_REACTIVATED = "AGENCY_REACTIVATED", "Agency reactivated"
    AGENCY_DEACTIVATED = "AGENCY_DEACTIVATED", "Agency deactivated"
    ROLE_CHANGED = "ROLE_CHANGED", "Role changed"
    SCHEDULE_CHANGED = "SCHEDULE_CHANGED", "Working schedule changed"
    SETTINGS_CHANGED = "SETTINGS_CHANGED", "Settings changed"
    RESOURCE_CHANGED = "RESOURCE_CHANGED", "Resource changed"
    CUSTOMER_CREATED = "CUSTOMER_CREATED", "Customer created"
    CUSTOMER_UPDATED = "CUSTOMER_UPDATED", "Customer updated"
    VEHICLE_CREATED = "VEHICLE_CREATED", "Vehicle created"
    VEHICLE_UPDATED = "VEHICLE_UPDATED", "Vehicle updated"
    VEHICLE_ARCHIVED = "VEHICLE_ARCHIVED", "Vehicle archived"
    INVENTORY_ADJUSTED = "INVENTORY_ADJUSTED", "Inventory adjusted"
    ADDITIONAL_WORK_REQUESTED = "ADDITIONAL_WORK_REQUESTED", "Additional work requested"
    ADDITIONAL_WORK_RESPONDED = "ADDITIONAL_WORK_RESPONDED", "Additional work responded"
    PAYMENT_REFUNDED = "PAYMENT_REFUNDED", "Payment refunded"
    INVOICE_VOIDED = "INVOICE_VOIDED", "Invoice voided"
    BOOKING_CREATED = "BOOKING_CREATED", "Booking created"
    BOOKING_UPDATED = "BOOKING_UPDATED", "Booking updated"
    BOOKING_CANCELLED = "BOOKING_CANCELLED", "Booking cancelled"
    PAYMENT_CHANGED = "PAYMENT_CHANGED", "Payment changed"
    INVOICE_CHANGED = "INVOICE_CHANGED", "Invoice changed"
    SERVICE_PRICE_CHANGED = "SERVICE_PRICE_CHANGED", "Service price changed"


class ImmutableRecordError(Exception):
    pass


class AuditLogQuerySet(TenantQuerySet):
    def update(self, **kwargs):
        raise ImmutableRecordError("Audit logs are append-only.")

    def delete(self):
        raise ImmutableRecordError("Audit logs are append-only.")


class AuditLog(UUIDModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="audit_logs"
    )
    organization = models.ForeignKey(
        "organizations.Organization", null=True, blank=True, on_delete=models.PROTECT, related_name="audit_logs"
    )
    action = models.CharField(max_length=64, choices=AuditAction.choices)
    model_name = models.CharField(max_length=100, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    old_data = models.JSONField(null=True, blank=True)
    new_data = models.JSONField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    objects = AuditLogQuerySet.as_manager()

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["organization", "-created_at"], name="audit_org_created_idx"),
            models.Index(fields=["user", "-created_at"], name="audit_user_created_idx"),
            models.Index(fields=["action", "-created_at"], name="audit_action_created_idx"),
            models.Index(fields=["model_name", "object_id"], name="audit_object_idx"),
        ]

    def __str__(self):
        return f"{self.action} {self.model_name}:{self.object_id} @ {self.created_at:%Y-%m-%d %H:%M}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ImmutableRecordError("Audit logs are append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableRecordError("Audit logs are append-only.")
