from django.db import transaction

from apps.accounts import tasks as account_tasks
from apps.accounts.constants import DEFAULT_MANAGER_PERMISSIONS, DEFAULT_STAFF_PERMISSIONS, Role, StaffPermission
from apps.accounts.models import User
from apps.accounts.services import AuthService
from apps.audit_logs.models import AuditAction
from apps.audit_logs.services import AuditService
from apps.core.exceptions import BusinessRuleViolation
from apps.organizations.models import Membership

from .models import AgencySettings, SpecialWorkingDay, WorkingHours

MANAGEABLE_ROLES = {Role.AGENCY_MANAGER, Role.AGENCY_STAFF}
SETTINGS_FIELDS = (
    "slot_interval_minutes", "buffer_minutes", "booking_lead_time_minutes", "max_advance_days",
    "cancellation_cutoff_hours", "auto_confirm_bookings", "additional_work_requires_approval",
    "require_online_payment",
)


def get_agency_settings(organization):
    settings_obj, _ = AgencySettings.objects.get_or_create(organization=organization)
    return settings_obj


def _clean_permissions(codes):
    codes = list(dict.fromkeys(str(c) for c in codes or []))
    invalid = set(codes) - set(StaffPermission.values)
    if invalid:
        raise BusinessRuleViolation(f"Unknown permission codes: {', '.join(sorted(invalid))}.",
                                    code="INVALID_PERMISSION_CODE")
    return sorted(codes)


def _ensure_can_manage(actor, target_user=None, role=None):
    """Agency admins manage managers & staff; only Super Admin manages agency admins."""
    if actor.is_super_admin:
        return
    if target_user is not None and target_user.pk == actor.pk:
        raise BusinessRuleViolation("You cannot change your own membership.", code="CANNOT_MODIFY_SELF")
    if (target_user is not None and target_user.role == Role.AGENCY_ADMIN) or role == Role.AGENCY_ADMIN:
        raise BusinessRuleViolation("Only a Super Admin can manage agency admins.", code="CANNOT_MANAGE_ADMIN")


class StaffService:
    @staticmethod
    @transaction.atomic
    def add_member(*, organization, actor, email, full_name, role, phone="", permissions=None, request=None):
        if role not in MANAGEABLE_ROLES | {Role.AGENCY_ADMIN}:
            raise BusinessRuleViolation("Role must be an agency role.", code="INVALID_ROLE")
        _ensure_can_manage(actor, role=role)
        email = email.strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            # Never attach an existing account to a tenant: that would leak/claim someone else's identity.
            raise BusinessRuleViolation("An account with this e-mail already exists.", code="EMAIL_TAKEN")

        if permissions is None:
            permissions = DEFAULT_MANAGER_PERMISSIONS if role == Role.AGENCY_MANAGER else DEFAULT_STAFF_PERMISSIONS
        permissions = [] if role == Role.AGENCY_ADMIN else _clean_permissions(permissions)

        user = User.objects.create_user(email=email, password=None, full_name=full_name, phone=phone, role=role)
        membership = Membership.objects.create(user=user, organization=organization, permissions=permissions,
                                               created_by=actor)
        AuditService.log(AuditAction.USER_CREATED, user=actor, organization=organization, instance=user,
                         request=request, new_data={"email": email, "role": role, "permissions": permissions})
        transaction.on_commit(
            lambda: account_tasks.send_staff_invite_email.delay(str(user.pk), organization.name)
        )
        return membership

    @staticmethod
    @transaction.atomic
    def update_member(*, membership, actor, data, request=None):
        membership = Membership.objects.select_for_update().select_related("user", "organization").get(
            pk=membership.pk)
        user = membership.user
        new_role = data.get("role", user.role)
        _ensure_can_manage(actor, target_user=user, role=new_role if "role" in data else None)
        if new_role not in MANAGEABLE_ROLES | ({Role.AGENCY_ADMIN} if actor.is_super_admin else set()):
            raise BusinessRuleViolation("Role must be AGENCY_MANAGER or AGENCY_STAFF.", code="INVALID_ROLE")

        user_fields = []
        for field in ("full_name", "phone"):
            if field in data and data[field] != getattr(user, field):
                setattr(user, field, data[field])
                user_fields.append(field)

        if new_role != user.role:
            AuditService.log(AuditAction.ROLE_CHANGED, user=actor, organization=membership.organization,
                             instance=user, request=request, old_data={"role": user.role},
                             new_data={"role": new_role})
            user.role = new_role
            user_fields.append("role")
        if user_fields:
            user.save(update_fields=[*user_fields, "updated_at"])

        if "permissions" in data:
            new_perms = [] if user.role == Role.AGENCY_ADMIN else _clean_permissions(data["permissions"])
            if sorted(membership.permissions or []) != new_perms:
                AuditService.log(AuditAction.PERMISSIONS_CHANGED, user=actor, organization=membership.organization,
                                 instance=membership, request=request,
                                 old_data={"permissions": sorted(membership.permissions or [])},
                                 new_data={"permissions": new_perms})
                membership.permissions = new_perms
                membership.save(update_fields=["permissions", "updated_at"])
        return membership

    @staticmethod
    @transaction.atomic
    def set_member_active(*, membership, actor, active, request=None):
        membership = Membership.objects.select_for_update().select_related("user", "organization").get(
            pk=membership.pk)
        user = membership.user
        _ensure_can_manage(actor, target_user=user)
        if membership.is_active == active and user.is_active == active:
            return membership
        if active and Membership.objects.filter(user=user, is_active=True).exclude(pk=membership.pk).exists():
            raise BusinessRuleViolation("This user is active in another agency.", code="MEMBERSHIP_CONFLICT")

        membership.is_active = active
        membership.save(update_fields=["is_active", "updated_at"])
        user.is_active = active
        user.save(update_fields=["is_active", "updated_at"])
        if not active:
            AuthService.revoke_all_refresh_tokens(user)
        AuditService.log(AuditAction.USER_ACTIVATED if active else AuditAction.USER_DEACTIVATED, user=actor,
                         organization=membership.organization, instance=user, request=request,
                         old_data={"is_active": not active}, new_data={"is_active": active})
        return membership


def _validate_intervals(intervals, key):
    """Intervals sharing ``key`` (weekday or date) must not overlap. Returns them sorted."""
    grouped = {}
    for item in intervals:
        if item["closes_at"] <= item["opens_at"]:
            raise BusinessRuleViolation("Closing time must be after opening time.", code="INVALID_INTERVAL",
                                        details={key: str(item[key])})
        grouped.setdefault(item[key], []).append(item)
    for group_key, items in grouped.items():
        items.sort(key=lambda i: i["opens_at"])
        for prev, cur in zip(items, items[1:]):
            if cur["opens_at"] < prev["closes_at"]:
                raise BusinessRuleViolation("Working intervals overlap.", code="OVERLAPPING_INTERVALS",
                                            details={key: str(group_key)})
    return [i for items in grouped.values() for i in items]


def _fmt(intervals, key):
    return sorted(
        [{key: str(i[key]), "opens_at": i["opens_at"].strftime("%H:%M"), "closes_at": i["closes_at"].strftime("%H:%M")}
         for i in intervals],
        key=lambda i: (i[key], i["opens_at"]),
    )


class ScheduleService:
    @staticmethod
    @transaction.atomic
    def replace_week(*, organization, intervals, actor, request=None):
        """Atomically replace the whole weekly schedule. Days without intervals are closed."""
        intervals = _validate_intervals(intervals, "weekday")
        existing = WorkingHours.objects.select_for_update().filter(organization=organization)
        old = _fmt(existing.values("weekday", "opens_at", "closes_at"), "weekday")
        existing.delete()
        rows = WorkingHours.objects.bulk_create(
            [WorkingHours(organization=organization, **i) for i in intervals]
        )
        AuditService.log(AuditAction.SCHEDULE_CHANGED, user=actor, organization=organization,
                         model_name="WorkingHours", object_id=str(organization.pk), request=request,
                         old_data={"week": old}, new_data={"week": _fmt(intervals, "weekday")})
        return sorted(rows, key=lambda r: (r.weekday, r.opens_at))

    @staticmethod
    @transaction.atomic
    def replace_special_day(*, organization, date, intervals, actor, request=None):
        """Set (or clear, with no intervals) the special hours for one date."""
        for i in intervals:
            i["date"] = date
        intervals = _validate_intervals(intervals, "date")
        existing = SpecialWorkingDay.objects.select_for_update().filter(organization=organization, date=date)
        old = _fmt(existing.values("date", "opens_at", "closes_at"), "date")
        existing.delete()
        rows = SpecialWorkingDay.objects.bulk_create(
            [SpecialWorkingDay(organization=organization, date=date, opens_at=i["opens_at"],
                               closes_at=i["closes_at"], note=i.get("note", "")) for i in intervals]
        )
        AuditService.log(AuditAction.SCHEDULE_CHANGED, user=actor, organization=organization,
                         model_name="SpecialWorkingDay", object_id=str(date), request=request,
                         old_data={"intervals": old}, new_data={"intervals": _fmt(intervals, "date")})
        return rows


class AgencySettingsService:
    @staticmethod
    @transaction.atomic
    def update(*, organization, data, actor, request=None):
        obj = AgencySettings.objects.select_for_update().get(pk=get_agency_settings(organization).pk)
        old, new = {}, {}
        for field in SETTINGS_FIELDS:
            if field in data and getattr(obj, field) != data[field]:
                old[field], new[field] = getattr(obj, field), data[field]
                setattr(obj, field, data[field])
        if new:
            obj.save(update_fields=[*new, "updated_at"])
            AuditService.log(AuditAction.SETTINGS_CHANGED, user=actor, organization=organization, instance=obj,
                             request=request, old_data=old, new_data=new)
        return obj
