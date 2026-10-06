import zoneinfo

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models

from apps.accounts.constants import Role, StaffPermission
from apps.accounts.models import phone_validator
from apps.core.models import BaseModel
from apps.core.storage import UploadPath, media_storage
from apps.core.tenancy import TenantManager, get_user_organization_id
from apps.core.validators import ImageFileValidator

gst_validator = RegexValidator(
    r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$", "Enter a valid 15-character GSTIN."
)
pincode_validator = RegexValidator(r"^[A-Za-z0-9 \-]{3,10}$", "Enter a valid postal code.")


def validate_timezone(value):
    if value not in zoneinfo.available_timezones():
        raise ValidationError(f"'{value}' is not a valid IANA timezone.")


def organization_tz(organization):
    return zoneinfo.ZoneInfo(organization.timezone or "Asia/Kolkata")


class OrganizationStatus(models.TextChoices):
    PENDING = "PENDING", "Pending approval"
    ACTIVE = "ACTIVE", "Active"
    INACTIVE = "INACTIVE", "Inactive"
    SUSPENDED = "SUSPENDED", "Suspended"
    REJECTED = "REJECTED", "Rejected"


class VerificationStatus(models.TextChoices):
    UNVERIFIED = "UNVERIFIED", "Unverified"
    PENDING = "PENDING", "Pending review"
    VERIFIED = "VERIFIED", "Verified"
    REJECTED = "REJECTED", "Rejected"


class OrganizationQuerySet(models.QuerySet):
    def for_user(self, user):
        """Super Admin sees every agency; agency users see only their own; everyone else nothing."""
        if user is None or not getattr(user, "is_authenticated", False):
            return self.none()
        if user.is_super_admin:
            return self
        org_id = get_user_organization_id(user)
        return self.filter(pk=org_id) if org_id else self.none()

    def bookable(self):
        """Only ACTIVE agencies may receive new bookings."""
        return self.filter(status=OrganizationStatus.ACTIVE)


class Organization(BaseModel):
    """An agency / vendor — the tenant boundary of the platform."""

    name = models.CharField(max_length=200)
    legal_name = models.CharField(max_length=255, blank=True)
    slug = models.SlugField(max_length=220, unique=True)
    logo = models.ImageField(
        upload_to=UploadPath("organizations/logos"), storage=media_storage, blank=True,
        validators=[ImageFileValidator(max_width=2048, max_height=2048)],
    )
    registration_number = models.CharField(max_length=64, blank=True)
    gst_number = models.CharField(max_length=15, blank=True, validators=[gst_validator])
    phone = models.CharField(max_length=16, validators=[phone_validator])
    email = models.EmailField()
    website = models.URLField(blank=True)
    description = models.TextField(blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, default="India")
    pincode = models.CharField(max_length=10, blank=True, validators=[pincode_validator])
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True,
                                   validators=[MinValueValidator(-90), MaxValueValidator(90)])
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True,
                                    validators=[MinValueValidator(-180), MaxValueValidator(180)])
    timezone = models.CharField(max_length=64, default="Asia/Kolkata", validators=[validate_timezone],
                                help_text="IANA zone used to interpret working hours and slots.")
    status = models.CharField(max_length=20, choices=OrganizationStatus.choices,
                              default=OrganizationStatus.PENDING)
    verification_status = models.CharField(max_length=20, choices=VerificationStatus.choices,
                                           default=VerificationStatus.PENDING)
    status_reason = models.TextField(blank=True)
    status_changed_at = models.DateTimeField(null=True, blank=True)

    objects = OrganizationQuerySet.as_manager()

    class Meta:
        ordering = ("name",)
        indexes = [
            models.Index(fields=["status"], name="org_status_idx"),
            models.Index(fields=["city", "status"], name="org_city_status_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(status__in=OrganizationStatus.values),
                                   name="org_status_valid"),
            models.CheckConstraint(condition=models.Q(verification_status__in=VerificationStatus.values),
                                   name="org_verification_status_valid"),
            models.CheckConstraint(
                condition=models.Q(latitude__isnull=True) | models.Q(latitude__gte=-90, latitude__lte=90),
                name="org_latitude_range",
            ),
            models.CheckConstraint(
                condition=models.Q(longitude__isnull=True) | models.Q(longitude__gte=-180, longitude__lte=180),
                name="org_longitude_range",
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def can_receive_bookings(self):
        return self.status == OrganizationStatus.ACTIVE


class Membership(BaseModel):
    """
    Links an agency user to their organization. An agency user has at most one
    *active* membership (DB-enforced), which is how the backend resolves the tenant.
    The user's agency role lives on ``User.role``; granular codes live here.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="memberships")
    permissions = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")

    objects = TenantManager()

    class Meta:
        ordering = ("created_at",)
        constraints = [
            models.UniqueConstraint(fields=["user", "organization"], name="membership_user_org_unique"),
            models.UniqueConstraint(fields=["user"], condition=models.Q(is_active=True),
                                    name="membership_one_active_per_user"),
        ]
        indexes = [models.Index(fields=["organization", "is_active"], name="membership_org_active_idx")]

    def __str__(self):
        return f"{self.user} @ {self.organization}"

    def has_permission(self, code):
        if not self.is_active:
            return False
        if self.user.role == Role.AGENCY_ADMIN:
            return True
        return code in (self.permissions or [])

    def clean(self):
        invalid = set(self.permissions or []) - set(StaffPermission.values)
        if invalid:
            raise ValidationError({"permissions": f"Unknown permission codes: {', '.join(sorted(invalid))}"})
