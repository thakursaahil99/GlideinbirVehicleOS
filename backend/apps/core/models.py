"""Abstract base models shared by every app."""
import uuid

from django.db import models

from .tenancy import TenantManager


class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class BaseModel(UUIDModel, TimeStampedModel):
    class Meta:
        abstract = True


class NumberSequence(models.Model):
    """Per-prefix, per-year counter for human-readable numbers (BK-2026-000001)."""

    prefix = models.CharField(max_length=10)
    year = models.PositiveSmallIntegerField()
    last_value = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["prefix", "year"], name="number_sequence_unique")]

    def __str__(self):
        return f"{self.prefix}-{self.year}: {self.last_value}"


class TenantModel(BaseModel):
    """
    A row owned by exactly one organization (tenant).

    Always query through ``Model.objects.for_user(request.user)`` in API code so
    tenant isolation is enforced from the authenticated user's membership.
    """

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.PROTECT,
        related_name="%(app_label)s_%(class)s_set",
    )

    objects = TenantManager()

    class Meta:
        abstract = True
