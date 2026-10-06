from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.accounts import tasks as account_tasks
from apps.accounts.constants import Role
from apps.accounts.models import User
from apps.audit_logs.models import AuditAction
from apps.audit_logs.services import AuditService, diff, snapshot
from apps.core.exceptions import BusinessRuleViolation, InvalidStateTransition

from .models import Membership, Organization, OrganizationStatus, VerificationStatus

PROFILE_FIELDS = (
    "name", "legal_name", "logo", "registration_number", "gst_number", "phone", "email", "website",
    "description", "address", "city", "state", "country", "pincode", "latitude", "longitude", "timezone",
)

# action -> (allowed source statuses, target status, verification status to set, audit action, reason required)
STATUS_TRANSITIONS = {
    "approve": (
        {OrganizationStatus.PENDING, OrganizationStatus.REJECTED},
        OrganizationStatus.ACTIVE, VerificationStatus.VERIFIED, AuditAction.AGENCY_APPROVED, False,
    ),
    "reject": (
        {OrganizationStatus.PENDING},
        OrganizationStatus.REJECTED, VerificationStatus.REJECTED, AuditAction.AGENCY_REJECTED, True,
    ),
    "suspend": (
        {OrganizationStatus.ACTIVE, OrganizationStatus.INACTIVE},
        OrganizationStatus.SUSPENDED, None, AuditAction.AGENCY_SUSPENDED, True,
    ),
    "reactivate": (
        {OrganizationStatus.SUSPENDED, OrganizationStatus.INACTIVE},
        OrganizationStatus.ACTIVE, None, AuditAction.AGENCY_REACTIVATED, False,
    ),
    "deactivate": (
        {OrganizationStatus.ACTIVE},
        OrganizationStatus.INACTIVE, None, AuditAction.AGENCY_DEACTIVATED, False,
    ),
}


def unique_slug(name, exclude_pk=None, max_length=200):
    base = slugify(name)[:max_length] or "agency"
    slug, n = base, 2
    while Organization.objects.filter(slug=slug).exclude(pk=exclude_pk).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug


class OrganizationService:
    @staticmethod
    @transaction.atomic
    def register_agency(*, organization_data, admin_data, request=None):
        """Create a PENDING agency plus its first Agency Admin. Super Admin approval is required to go live."""
        org = Organization.objects.create(
            **organization_data,
            slug=unique_slug(organization_data["name"]),
            status=OrganizationStatus.PENDING,
            verification_status=VerificationStatus.PENDING,
        )
        admin = User.objects.create_user(
            email=admin_data["email"], password=admin_data["password"], full_name=admin_data["full_name"],
            phone=admin_data.get("phone", ""), role=Role.AGENCY_ADMIN,
        )
        Membership.objects.create(user=admin, organization=org, permissions=[], created_by=admin)

        AuditService.log(AuditAction.AGENCY_REGISTERED, user=admin, organization=org, instance=org,
                         request=request, new_data=snapshot(org, fields=["name", "email", "city", "status"]))
        AuditService.log(AuditAction.USER_CREATED, user=admin, organization=org, instance=admin, request=request,
                         new_data={"email": admin.email, "role": admin.role})
        transaction.on_commit(lambda: account_tasks.send_verification_email.delay(str(admin.pk)))
        return org, admin

    @staticmethod
    @transaction.atomic
    def create_agency(*, organization_data, admin_data, actor, request=None):
        """Super Admin onboards an agency directly: it is ACTIVE and VERIFIED straight away."""
        from apps.vendors.services import StaffService

        org = Organization.objects.create(
            **organization_data,
            slug=unique_slug(organization_data["name"]),
            status=OrganizationStatus.ACTIVE,
            verification_status=VerificationStatus.VERIFIED,
            status_changed_at=timezone.now(),
        )
        AuditService.log(AuditAction.AGENCY_REGISTERED, user=actor, organization=org, instance=org,
                         request=request, new_data=snapshot(org, fields=["name", "email", "city", "status"]))
        StaffService.add_member(organization=org, actor=actor, email=admin_data["email"],
                                full_name=admin_data["full_name"], phone=admin_data.get("phone", ""),
                                role=Role.AGENCY_ADMIN, password=admin_data.get("password") or None,
                                request=request)
        return org

    @staticmethod
    @transaction.atomic
    def change_status(*, organization, action, actor, reason="", request=None):
        if action not in STATUS_TRANSITIONS:
            raise BusinessRuleViolation(f"Unknown status action '{action}'.")
        allowed_from, target, verification, audit_action, reason_required = STATUS_TRANSITIONS[action]
        if reason_required and not reason.strip():
            raise BusinessRuleViolation("A reason is required for this action.", code="REASON_REQUIRED")

        # Lock the row so two admins cannot apply conflicting transitions concurrently.
        org = Organization.objects.select_for_update().get(pk=organization.pk)
        if org.status not in allowed_from:
            raise InvalidStateTransition(
                f"Cannot {action} an agency whose status is {org.status}.",
                details={"current_status": org.status, "allowed_from": sorted(allowed_from)},
            )

        old = {"status": org.status, "verification_status": org.verification_status}
        org.status = target
        if verification:
            org.verification_status = verification
        org.status_reason = reason.strip()
        org.status_changed_at = timezone.now()
        org.save(update_fields=["status", "verification_status", "status_reason", "status_changed_at",
                                "updated_at"])
        AuditService.log(audit_action, user=actor, organization=org, instance=org, request=request,
                         old_data=old, new_data={"status": org.status,
                                                 "verification_status": org.verification_status,
                                                 "reason": org.status_reason})
        return org

    @staticmethod
    @transaction.atomic
    def update_profile(*, organization, data, actor, request=None):
        fields = [f for f in PROFILE_FIELDS if f in data]
        if not fields:
            return organization
        before = snapshot(organization, fields=fields)
        for field in fields:
            setattr(organization, field, data[field])
        update_fields = [*fields, "updated_at"]
        if "name" in fields:
            organization.slug = unique_slug(organization.name, exclude_pk=organization.pk)
            update_fields.append("slug")
        organization.save(update_fields=update_fields)
        old, new = diff(before, snapshot(organization, fields=fields))
        if old or new:
            AuditService.log(AuditAction.AGENCY_UPDATED, user=actor, organization=organization,
                             instance=organization, request=request, old_data=old, new_data=new)
        return organization
