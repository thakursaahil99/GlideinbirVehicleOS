"""
Customers are platform-level people. An agency only sees a customer through an
``AgencyCustomer`` link (created by a booking, or when the agency registers a
walk-in). Internal notes are tenant-private (``CustomerNote``).
"""
from django.conf import settings
from django.db import models

from apps.accounts.models import phone_validator
from apps.core.models import BaseModel, TenantModel
from apps.core.tenancy import get_user_organization_id


class CustomerQuerySet(models.QuerySet):
    def for_user(self, user):
        if user is None or not getattr(user, "is_authenticated", False):
            return self.none()
        if user.is_super_admin:
            return self
        if user.is_customer:
            return self.filter(user=user)
        org_id = get_user_organization_id(user)
        if org_id is None:
            return self.none()
        return self.filter(agency_links__organization_id=org_id)


class Customer(BaseModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                                related_name="customer_profile")
    owner_organization = models.ForeignKey(
        "organizations.Organization", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
        help_text="Set for walk-in customers created by an agency (they own the record).",
    )
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=16, blank=True, validators=[phone_validator], db_index=True)
    email = models.EmailField(blank=True, db_index=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, default="India")
    pincode = models.CharField(max_length=10, blank=True)
    notes = models.TextField(blank=True, help_text="Customer's own notes (e.g. preferred contact time).")

    objects = CustomerQuerySet.as_manager()

    class Meta:
        ordering = ("full_name",)
        indexes = [models.Index(fields=["full_name"], name="customer_name_idx")]

    def __str__(self):
        return self.full_name

    @property
    def is_walk_in(self):
        return self.user_id is None


class CustomerSource(models.TextChoices):
    BOOKING = "BOOKING", "Online booking"
    WALK_IN = "WALK_IN", "Walk-in / added by agency"


class AgencyCustomer(TenantModel):
    """Which agencies a customer has a relationship with — the tenant gate for customer data."""

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="agency_links")
    source = models.CharField(max_length=20, choices=CustomerSource.choices, default=CustomerSource.BOOKING)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["organization", "customer"], name="agency_customer_unique")]

    def __str__(self):
        return f"{self.customer} @ {self.organization}"


class CustomerNote(TenantModel):
    """Internal note written by agency staff. Never shown to the customer or other agencies."""

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="internal_notes")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    body = models.TextField(max_length=4000)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["organization", "customer", "-created_at"], name="customer_note_idx")]
