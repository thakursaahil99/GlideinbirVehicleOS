"""
BookingService — creation, lifecycle transitions, cancellation and rescheduling.

Double-booking prevention:
1. Every create/reschedule runs in ONE transaction that first locks the
   VendorService row (and all resources of the required type) with
   SELECT ... FOR UPDATE, so concurrent requests for the same capacity
   serialize.
2. Availability (capacity, resources, conflicts, buffer) is recomputed inside
   that lock with fresh reads.
3. PostgreSQL additionally enforces "one resource, one active booking at a time"
   with an exclusion constraint (see migration 0002).
"""
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.constants import StaffPermission
from apps.audit_logs.models import AuditAction
from apps.audit_logs.services import AuditService
from apps.availability.services import AvailabilityService, SlotUnavailable
from apps.core.exceptions import BusinessRuleViolation, InvalidStateTransition
from apps.core.numbering import next_number
from apps.core.tenancy import get_user_membership
from apps.customers.models import Customer, CustomerSource
from apps.customers.services import CustomerService
from apps.organizations.models import Membership
from apps.services.models import VendorService
from apps.vehicles.models import Vehicle
from apps.vendors.models import ServiceResource
from apps.vendors.services import get_agency_settings

from . import events
from .models import (
    ACTIVE_STATUSES,
    Booking,
    BookingReschedule,
    BookingSource,
    BookingStatus,
    BookingStatusHistory,
)

S = BookingStatus

# action -> (allowed from, to, staff permission needed)
TRANSITIONS = {
    "confirm": ({S.PENDING}, S.CONFIRMED, StaffPermission.BOOKING_UPDATE),
    "reject": ({S.PENDING}, S.REJECTED, StaffPermission.BOOKING_UPDATE),
    "receive_vehicle": ({S.CONFIRMED, S.ASSIGNED}, S.VEHICLE_RECEIVED, StaffPermission.BOOKING_UPDATE),
    "start": ({S.VEHICLE_RECEIVED, S.WAITING_FOR_APPROVAL}, S.IN_PROGRESS, StaffPermission.BOOKING_UPDATE),
    "complete": ({S.IN_PROGRESS, S.WAITING_FOR_APPROVAL}, S.COMPLETED, StaffPermission.BOOKING_UPDATE),
    "no_show": ({S.CONFIRMED, S.ASSIGNED}, S.NO_SHOW, StaffPermission.BOOKING_UPDATE),
}
CUSTOMER_CANCELLABLE = {S.PENDING, S.CONFIRMED, S.ASSIGNED}
AGENCY_CANCELLABLE = {S.PENDING, S.CONFIRMED, S.ASSIGNED, S.VEHICLE_RECEIVED}
RESCHEDULABLE = {S.PENDING, S.CONFIRMED, S.ASSIGNED}


def _require_agency_perm(actor, booking, code):
    if actor.is_super_admin:
        return
    membership = get_user_membership(actor)
    if membership is None or membership.organization_id != booking.organization_id:
        raise BusinessRuleViolation("Booking not found.", code="NOT_FOUND", status_code=404)
    if not membership.has_permission(code):
        raise BusinessRuleViolation("You do not have permission to perform this action.",
                                    code="PERMISSION_DENIED", status_code=403)


def _record(booking, from_status, actor, note=""):
    BookingStatusHistory.objects.create(booking=booking, from_status=from_status or "", to_status=booking.status,
                                        changed_by=actor, note=note)


def _lock_capacity(vendor_service):
    """Serialize all bookings competing for this service's capacity and resources."""
    vs = VendorService.objects.select_for_update().select_related("service", "organization").get(pk=vendor_service.pk)
    if vs.required_resource_type:
        list(ServiceResource.objects.select_for_update()
             .filter(organization=vs.organization, resource_type=vs.required_resource_type)
             .order_by("pk").values_list("pk", flat=True))
    return vs


class BookingService:
    # ------------------------------------------------------------------ create
    @staticmethod
    def _resolve_parties(*, actor, vehicle_id, vendor_service_id, customer_id):
        vs = VendorService.objects.select_related("service", "organization").filter(pk=vendor_service_id).first()
        if actor.is_customer:
            customer = Customer.objects.filter(user=actor).first() or CustomerService.ensure_profile(actor)
            if vs is None or not VendorService.objects.bookable().filter(pk=vs.pk).exists():
                raise BusinessRuleViolation("This service is not available for online booking.",
                                            code="SERVICE_NOT_BOOKABLE")
            source = BookingSource.ONLINE
        else:
            membership = get_user_membership(actor)
            if membership is None or not membership.has_permission(StaffPermission.BOOKING_CREATE):
                raise BusinessRuleViolation("You do not have permission to create bookings.",
                                            code="PERMISSION_DENIED", status_code=403)
            if vs is None or vs.organization_id != membership.organization_id:
                raise BusinessRuleViolation("Service not found.", code="SERVICE_NOT_FOUND", status_code=404)
            customer = Customer.objects.for_user(actor).filter(pk=customer_id).first() if customer_id else None
            if customer is None:
                raise BusinessRuleViolation("Customer not found.", code="CUSTOMER_NOT_FOUND", status_code=404)
            source = BookingSource.AGENCY

        vehicle = Vehicle.objects.filter(pk=vehicle_id, customer=customer, is_active=True).first()
        if vehicle is None:
            # Never reveal whether someone else's vehicle exists.
            raise BusinessRuleViolation("Vehicle not found.", code="VEHICLE_NOT_FOUND", status_code=404)
        if vehicle.vehicle_type not in (vs.service.supported_vehicle_types or []):
            raise BusinessRuleViolation(f"{vs.service.name} is not available for this vehicle type.",
                                        code="VEHICLE_TYPE_NOT_SUPPORTED")
        return customer, vehicle, vs, source

    @staticmethod
    def _check_vehicle_free(vehicle, start, end, exclude_pk=None):
        qs = Booking.objects.filter(vehicle=vehicle, status__in=ACTIVE_STATUSES,
                                    start_datetime__lt=end, end_datetime__gt=start)
        if exclude_pk:
            qs = qs.exclude(pk=exclude_pk)
        if qs.exists():
            raise BusinessRuleViolation("This vehicle already has a booking at that time.",
                                        code="VEHICLE_ALREADY_BOOKED", status_code=409)

    @staticmethod
    def create(*, actor, vehicle_id, vendor_service_id, start_datetime, customer_id=None, customer_notes="",
               pickup_requested=False, drop_requested=False, pickup_address="", request=None):
        customer, vehicle, vs, source = BookingService._resolve_parties(
            actor=actor, vehicle_id=vehicle_id, vendor_service_id=vendor_service_id, customer_id=customer_id)
        if pickup_requested and not vs.pickup_available:
            raise BusinessRuleViolation("Pickup is not offered for this service.", code="PICKUP_NOT_AVAILABLE")
        if drop_requested and not vs.drop_available:
            raise BusinessRuleViolation("Drop is not offered for this service.", code="DROP_NOT_AVAILABLE")
        if pickup_requested and not pickup_address.strip():
            raise BusinessRuleViolation("A pickup address is required.", code="PICKUP_ADDRESS_REQUIRED")

        try:
            with transaction.atomic():
                vs = _lock_capacity(vs)
                availability = AvailabilityService(vs, enforce_lead_time=source == BookingSource.ONLINE)
                slot = availability.check_slot(start_datetime)
                BookingService._check_vehicle_free(vehicle, slot.start, slot.end)
                settings_obj = availability.settings

                status = S.CONFIRMED if settings_obj.auto_confirm_bookings else S.PENDING
                now = timezone.now()
                booking = Booking.objects.create(
                    organization=vs.organization,
                    booking_number=next_number("BK"),
                    customer=customer, vehicle=vehicle, vendor_service=vs,
                    booking_date=slot.start.astimezone(availability.tz).date(),
                    start_datetime=slot.start, end_datetime=slot.end,
                    status=status, source=source,
                    assigned_resource_id=slot.free_resource_ids[0] if slot.free_resource_ids else None,
                    customer_notes=customer_notes, pickup_requested=pickup_requested,
                    drop_requested=drop_requested, pickup_address=pickup_address,
                    quoted_price=vs.price, tax_rate=vs.tax_rate, duration_minutes=vs.duration,
                    created_by=actor, confirmed_at=now if status == S.CONFIRMED else None,
                )
                _record(booking, "", actor, "Booking created")
                CustomerService.link_to_agency(customer, vs.organization, CustomerSource.BOOKING)
                AuditService.log(AuditAction.BOOKING_CREATED, user=actor, organization=vs.organization,
                                 instance=booking, request=request,
                                 new_data={"booking_number": booking.booking_number, "status": booking.status,
                                           "start": slot.start.isoformat(), "service": vs.service.name,
                                           "price": str(booking.quoted_price)})
                events.booking_created(booking, settings_obj)
        except IntegrityError as exc:
            # The DB exclusion constraint caught a race the lock could not (defence in depth).
            raise SlotUnavailable() from exc
        return booking

    # ------------------------------------------------------------------ lifecycle
    @staticmethod
    @transaction.atomic
    def transition(*, booking, action, actor, note="", request=None):
        if action not in TRANSITIONS:
            raise BusinessRuleViolation(f"Unknown action '{action}'.")
        allowed_from, target, perm = TRANSITIONS[action]
        _require_agency_perm(actor, booking, perm)
        booking = Booking.objects.select_for_update().get(pk=booking.pk)
        if booking.status not in allowed_from:
            raise InvalidStateTransition(
                f"Cannot {action.replace('_', ' ')} a booking that is {booking.get_status_display().lower()}.",
                details={"current_status": booking.status, "allowed_from": sorted(allowed_from)})
        if action == "no_show" and timezone.now() < booking.start_datetime:
            raise BusinessRuleViolation("A booking can be marked no-show only after its start time.",
                                        code="TOO_EARLY_FOR_NO_SHOW")
        previous = booking.status
        booking.status = target
        fields = ["status", "updated_at"]
        if target == S.CONFIRMED:
            booking.confirmed_at = timezone.now()
            fields.append("confirmed_at")
        if target == S.COMPLETED:
            booking.completed_at = timezone.now()
            fields.append("completed_at")
        if target == S.REJECTED:
            booking.cancellation_reason, booking.cancelled_by = note, actor
            booking.cancelled_at = timezone.now()
            fields += ["cancellation_reason", "cancelled_by", "cancelled_at"]
        booking.save(update_fields=fields)
        _record(booking, previous, actor, note)
        AuditService.log(AuditAction.BOOKING_UPDATED, user=actor, organization=booking.organization,
                         instance=booking, request=request, old_data={"status": previous},
                         new_data={"status": target, "note": note})
        events.booking_status_changed(booking, previous, action)
        return booking

    @staticmethod
    @transaction.atomic
    def assign(*, booking, actor, staff_id=None, resource_id=None, request=None):
        _require_agency_perm(actor, booking, StaffPermission.BOOKING_UPDATE)
        booking = Booking.objects.select_for_update().get(pk=booking.pk)
        if booking.status not in (S.PENDING, S.CONFIRMED, S.ASSIGNED, S.VEHICLE_RECEIVED, S.IN_PROGRESS,
                                  S.WAITING_FOR_APPROVAL):
            raise InvalidStateTransition("Only active bookings can be assigned.")
        old = {"staff": str(booking.assigned_staff_id or ""), "resource": str(booking.assigned_resource_id or "")}
        window = (booking.start_datetime, booking.end_datetime)

        if staff_id is not None:
            membership = Membership.objects.filter(user_id=staff_id, organization=booking.organization,
                                                   is_active=True).select_related("user").first()
            if membership is None:
                raise BusinessRuleViolation("Staff member not found in this agency.", code="STAFF_NOT_FOUND")
            clash = Booking.objects.filter(assigned_staff_id=staff_id, status__in=ACTIVE_STATUSES).overlapping(
                *window).exclude(pk=booking.pk)
            if clash.exists():
                raise BusinessRuleViolation("This staff member is busy at that time.", code="STAFF_CONFLICT",
                                            status_code=409)
            booking.assigned_staff_id = staff_id

        if resource_id is not None:
            resource = ServiceResource.objects.select_for_update().filter(
                pk=resource_id, organization=booking.organization, active=True).first()
            if resource is None:
                raise BusinessRuleViolation("Resource not found.", code="RESOURCE_NOT_FOUND")
            buffer = timedelta(minutes=get_agency_settings(booking.organization).buffer_minutes)
            clash = Booking.objects.filter(assigned_resource=resource, status__in=ACTIVE_STATUSES).overlapping(
                window[0] - buffer, window[1] + buffer).exclude(pk=booking.pk)
            if clash.exists():
                raise BusinessRuleViolation("This resource is already booked at that time.",
                                            code="RESOURCE_CONFLICT", status_code=409)
            booking.assigned_resource = resource

        previous = booking.status
        if booking.status == S.CONFIRMED and booking.assigned_staff_id:
            booking.status = S.ASSIGNED
        booking.save()
        if previous != booking.status:
            _record(booking, previous, actor, "Staff assigned")
        AuditService.log(AuditAction.BOOKING_UPDATED, user=actor, organization=booking.organization,
                         instance=booking, request=request, old_data=old,
                         new_data={"staff": str(booking.assigned_staff_id or ""),
                                   "resource": str(booking.assigned_resource_id or "")})
        return booking

    # ------------------------------------------------------------------ cancel / reschedule
    @staticmethod
    def _check_customer_cutoff(booking, actor, verb):
        if not actor.is_customer:
            return
        cutoff = get_agency_settings(booking.organization).cancellation_cutoff_hours
        if booking.start_datetime - timezone.now() < timedelta(hours=cutoff):
            raise BusinessRuleViolation(
                f"Bookings can't be {verb} less than {cutoff} hours before the start. Please call the agency.",
                code="CUTOFF_PASSED")

    @staticmethod
    @transaction.atomic
    def cancel(*, booking, actor, reason, request=None):
        if not reason.strip():
            raise BusinessRuleViolation("A cancellation reason is required.", code="REASON_REQUIRED")
        booking = Booking.objects.select_for_update().get(pk=booking.pk)
        if actor.is_customer:
            if booking.customer.user_id != actor.pk:
                raise BusinessRuleViolation("Booking not found.", code="NOT_FOUND", status_code=404)
            allowed = CUSTOMER_CANCELLABLE
            BookingService._check_customer_cutoff(booking, actor, "cancelled")
        else:
            _require_agency_perm(actor, booking, StaffPermission.BOOKING_CANCEL)
            allowed = AGENCY_CANCELLABLE
        if booking.status not in allowed:
            raise InvalidStateTransition(f"A {booking.get_status_display().lower()} booking can't be cancelled.",
                                         details={"current_status": booking.status})
        previous = booking.status
        booking.status = S.CANCELLED
        booking.cancelled_at, booking.cancelled_by, booking.cancellation_reason = timezone.now(), actor, reason.strip()
        booking.save(update_fields=["status", "cancelled_at", "cancelled_by", "cancellation_reason", "updated_at"])
        _record(booking, previous, actor, reason.strip())
        AuditService.log(AuditAction.BOOKING_CANCELLED, user=actor, organization=booking.organization,
                         instance=booking, request=request, old_data={"status": previous},
                         new_data={"status": S.CANCELLED, "reason": reason.strip(),
                                   "by_role": actor.role})
        events.booking_cancelled(booking, actor)
        return booking

    @staticmethod
    def reschedule(*, booking, actor, start_datetime, reason="", request=None):
        if actor.is_customer:
            if booking.customer.user_id != actor.pk:
                raise BusinessRuleViolation("Booking not found.", code="NOT_FOUND", status_code=404)
            BookingService._check_customer_cutoff(booking, actor, "rescheduled")
        else:
            _require_agency_perm(actor, booking, StaffPermission.BOOKING_UPDATE)
        try:
            with transaction.atomic():
                vs = _lock_capacity(booking.vendor_service)
                booking = Booking.objects.select_for_update().get(pk=booking.pk)
                if booking.status not in RESCHEDULABLE:
                    raise InvalidStateTransition(
                        f"A {booking.get_status_display().lower()} booking can't be rescheduled.",
                        details={"current_status": booking.status})
                availability = AvailabilityService(vs, enforce_lead_time=actor.is_customer)
                slot = availability.check_slot(start_datetime, exclude_booking_id=booking.pk)
                BookingService._check_vehicle_free(booking.vehicle, slot.start, slot.end, exclude_pk=booking.pk)

                history = BookingReschedule(
                    booking=booking, old_start=booking.start_datetime, old_end=booking.end_datetime,
                    new_start=slot.start, new_end=slot.end, old_resource=booking.assigned_resource,
                    reason=reason, rescheduled_by=actor,
                )
                if booking.assigned_resource_id and booking.assigned_resource_id not in slot.free_resource_ids:
                    booking.assigned_resource_id = slot.free_resource_ids[0] if slot.free_resource_ids else None
                elif not booking.assigned_resource_id and slot.free_resource_ids:
                    booking.assigned_resource_id = slot.free_resource_ids[0]
                if booking.assigned_staff_id and Booking.objects.filter(
                        assigned_staff_id=booking.assigned_staff_id, status__in=ACTIVE_STATUSES).overlapping(
                        slot.start, slot.end).exclude(pk=booking.pk).exists():
                    booking.assigned_staff_id = None  # staff busy at the new time — reassign later
                    if booking.status == S.ASSIGNED:
                        booking.status = S.CONFIRMED
                booking.start_datetime, booking.end_datetime = slot.start, slot.end
                booking.booking_date = slot.start.astimezone(availability.tz).date()
                booking.reminder_sent_at = None
                booking.save()
                history.new_resource_id = booking.assigned_resource_id
                history.save()
                AuditService.log(AuditAction.BOOKING_UPDATED, user=actor, organization=booking.organization,
                                 instance=booking, request=request,
                                 old_data={"start": history.old_start.isoformat()},
                                 new_data={"start": slot.start.isoformat(), "reason": reason, "rescheduled": True})
                events.booking_rescheduled(booking, history)
        except IntegrityError as exc:
            raise SlotUnavailable() from exc
        return booking

    # ------------------------------------------------------------------ edits
    @staticmethod
    @transaction.atomic
    def update_notes(*, booking, actor, data, request=None):
        """Controlled editing: customers edit their notes on open bookings; agencies edit internal notes."""
        fields = []
        if "customer_notes" in data:
            if not actor.is_customer:
                raise BusinessRuleViolation("Only the customer edits customer notes.", code="FIELD_NOT_EDITABLE",
                                            status_code=403)
            if booking.status not in CUSTOMER_CANCELLABLE:
                raise BusinessRuleViolation("Notes can't be changed once work has started.",
                                            code="BOOKING_LOCKED")
            booking.customer_notes = data["customer_notes"]
            fields.append("customer_notes")
        if "internal_notes" in data:
            if actor.is_customer:
                raise BusinessRuleViolation("Internal notes are agency-only.", code="FIELD_NOT_EDITABLE",
                                            status_code=403)
            _require_agency_perm(actor, booking, StaffPermission.BOOKING_UPDATE)
            booking.internal_notes = data["internal_notes"]
            fields.append("internal_notes")
        if fields:
            booking.save(update_fields=[*fields, "updated_at"])
        return booking


def allowed_actions(booking, user):
    """What the UI may offer this user for this booking (the API still re-checks everything)."""
    if user.is_customer:
        actions = []
        if booking.status in CUSTOMER_CANCELLABLE and booking.start_datetime > timezone.now():
            actions += ["cancel", "reschedule"]
        return actions
    membership = get_user_membership(user)
    if not user.is_super_admin and (membership is None or membership.organization_id != booking.organization_id):
        return []

    def can(code):
        return user.is_super_admin or membership.has_permission(code)

    actions = [a for a, (frm, _to, perm) in TRANSITIONS.items() if booking.status in frm and can(perm)]
    if booking.status in AGENCY_CANCELLABLE and can(StaffPermission.BOOKING_CANCEL):
        actions.append("cancel")
    if booking.status in RESCHEDULABLE and can(StaffPermission.BOOKING_UPDATE):
        actions.append("reschedule")
    if booking.status in ACTIVE_STATUSES and can(StaffPermission.BOOKING_UPDATE):
        actions.append("assign")
    return actions
