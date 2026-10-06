"""
JobCardService — the workshop side of a booking.

A job card opens automatically when the vehicle is received. Status moves
OPEN → INSPECTION → WORK_IN_PROGRESS ⇄ WAITING_APPROVAL → COMPLETED → CLOSED and
keeps the booking in sync (IN_PROGRESS / WAITING_FOR_APPROVAL / COMPLETED).
"""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.accounts.constants import StaffPermission
from apps.audit_logs.models import AuditAction
from apps.audit_logs.services import AuditService
from apps.bookings.models import Booking, BookingStatus, BookingStatusHistory
from apps.core.exceptions import BusinessRuleViolation, InvalidStateTransition
from apps.core.numbering import next_number
from apps.core.tenancy import get_user_membership
from apps.inventory.models import Part, TransactionType
from apps.inventory.services import InventoryService
from apps.notifications.models import Event
from apps.vendors.services import get_agency_settings

from .models import (
    AdditionalWorkRequest,
    AdditionalWorkStatus,
    InspectionItem,
    JobCard,
    JobCardPart,
    JobCardStatus,
)

J = JobCardStatus
EDITABLE = {J.OPEN, J.INSPECTION, J.WORK_IN_PROGRESS, J.WAITING_APPROVAL}
DETAIL_FIELDS = ("inspection_notes", "vehicle_condition", "odometer", "fuel_level", "existing_damage",
                 "customer_requests", "technician_notes")


def require_job_perm(actor, job_card, code=StaffPermission.JOB_CARD_UPDATE):
    if actor.is_super_admin:
        return
    membership = get_user_membership(actor)
    if membership is None or membership.organization_id != job_card.organization_id:
        raise BusinessRuleViolation("Job card not found.", code="NOT_FOUND", status_code=404)
    if not membership.has_permission(code):
        raise BusinessRuleViolation("You do not have permission to update job cards.", code="PERMISSION_DENIED",
                                    status_code=403)


def _sync_booking(job_card, booking_status, actor, note):
    booking = Booking.objects.select_for_update().get(pk=job_card.booking_id)
    if booking.status != booking_status:
        previous = booking.status
        booking.status = booking_status
        fields = ["status", "updated_at"]
        if booking_status == BookingStatus.COMPLETED:
            booking.completed_at = timezone.now()
            fields.append("completed_at")
        booking.save(update_fields=fields)
        BookingStatusHistory.objects.create(booking=booking, from_status=previous, to_status=booking_status,
                                            changed_by=actor, note=note)
    return booking


class JobCardService:
    @staticmethod
    def open_for_booking(booking):
        """Called when the vehicle is received (inside the booking transaction). Idempotent."""
        existing = JobCard.objects.filter(booking=booking).first()
        if existing:
            return existing
        return JobCard.objects.create(
            organization=booking.organization, booking=booking, vehicle=booking.vehicle, customer=booking.customer,
            job_card_number=next_number("JOB"), customer_requests=booking.customer_notes,
            odometer=booking.vehicle.odometer,
        )

    @staticmethod
    @transaction.atomic
    def update_details(*, job_card, actor, data):
        require_job_perm(actor, job_card)
        job_card = JobCard.objects.select_for_update().get(pk=job_card.pk)
        if job_card.status not in EDITABLE:
            raise BusinessRuleViolation("Completed job cards can't be edited.", code="JOB_CARD_LOCKED")
        fields = [f for f in DETAIL_FIELDS if f in data]
        for f in fields:
            setattr(job_card, f, data[f])
        if fields:
            job_card.save(update_fields=[*fields, "updated_at"])
            if "odometer" in fields and data["odometer"]:
                vehicle = job_card.vehicle
                if not vehicle.odometer or data["odometer"] > vehicle.odometer:
                    vehicle.odometer = data["odometer"]
                    vehicle.save(update_fields=["odometer", "updated_at"])
        return job_card

    @staticmethod
    @transaction.atomic
    def save_inspection(*, job_card, actor, items):
        require_job_perm(actor, job_card)
        if job_card.status not in EDITABLE:
            raise BusinessRuleViolation("Completed job cards can't be edited.", code="JOB_CARD_LOCKED")
        saved = []
        for item in items:
            obj, _ = InspectionItem.objects.update_or_create(
                job_card=job_card, area=item["area"], stage=item.get("stage", "BEFORE"),
                defaults={"result": item["result"], "notes": item.get("notes", ""), "inspected_by": actor},
            )
            saved.append(obj)
        if job_card.status == J.OPEN:
            job_card.status = J.INSPECTION
            job_card.save(update_fields=["status", "updated_at"])
        return saved

    @staticmethod
    @transaction.atomic
    def start_work(*, job_card, actor):
        require_job_perm(actor, job_card)
        job_card = JobCard.objects.select_for_update().get(pk=job_card.pk)
        if job_card.status not in (J.OPEN, J.INSPECTION):
            raise InvalidStateTransition("Work can start only after the vehicle is received / inspected.",
                                         details={"current_status": job_card.status})
        job_card.status = J.WORK_IN_PROGRESS
        job_card.save(update_fields=["status", "updated_at"])
        booking = _sync_booking(job_card, BookingStatus.IN_PROGRESS, actor, "Work started")
        from apps.bookings import events

        events.notify_customer(booking, Event.SERVICE_STARTED)
        return job_card

    @staticmethod
    def _refresh_waiting(job_card, actor):
        pending = job_card.additional_work.filter(status=AdditionalWorkStatus.PENDING).exists()
        if pending and job_card.status == J.WORK_IN_PROGRESS:
            job_card.status = J.WAITING_APPROVAL
            job_card.save(update_fields=["status", "updated_at"])
            _sync_booking(job_card, BookingStatus.WAITING_FOR_APPROVAL, actor, "Waiting for customer approval")
        elif not pending and job_card.status == J.WAITING_APPROVAL:
            job_card.status = J.WORK_IN_PROGRESS
            job_card.save(update_fields=["status", "updated_at"])
            _sync_booking(job_card, BookingStatus.IN_PROGRESS, actor, "Approval received")

    @staticmethod
    @transaction.atomic
    def request_additional_work(*, job_card, actor, description, estimated_cost, request=None):
        require_job_perm(actor, job_card)
        job_card = JobCard.objects.select_for_update().get(pk=job_card.pk)
        if job_card.status not in (J.INSPECTION, J.WORK_IN_PROGRESS, J.WAITING_APPROVAL):
            raise InvalidStateTransition("Additional work can be raised during inspection or work.")
        needs_approval = get_agency_settings(job_card.organization).additional_work_requires_approval
        now = timezone.now()
        req = AdditionalWorkRequest.objects.create(
            job_card=job_card, description=description, estimated_cost=Decimal(estimated_cost), requested_by=actor,
            status=AdditionalWorkStatus.PENDING if needs_approval else AdditionalWorkStatus.APPROVED,
            approved_at=None if needs_approval else now, auto_approved=not needs_approval,
        )
        AuditService.log(AuditAction.ADDITIONAL_WORK_REQUESTED, user=actor, organization=job_card.organization,
                         instance=req, request=request,
                         new_data={"job_card": job_card.job_card_number, "description": description[:200],
                                   "estimated_cost": str(req.estimated_cost), "auto_approved": req.auto_approved})
        JobCardService._refresh_waiting(job_card, actor)
        if needs_approval:
            from apps.bookings import events

            events.notify_customer(job_card.booking, Event.ADDITIONAL_WORK_REQUESTED, description=description[:120],
                                   amount=f"{req.estimated_cost:,.2f}")
        return req

    @staticmethod
    @transaction.atomic
    def respond_additional_work(*, work_request, actor, approve, response="", request=None):
        req = AdditionalWorkRequest.objects.select_for_update().select_related("job_card__customer").get(
            pk=work_request.pk)
        job_card = req.job_card
        if actor.is_customer:
            if job_card.customer.user_id != actor.pk:
                raise BusinessRuleViolation("Request not found.", code="NOT_FOUND", status_code=404)
        else:
            # Agencies record a customer's verbal/phone decision on their behalf.
            require_job_perm(actor, job_card)
        if req.status != AdditionalWorkStatus.PENDING:
            raise InvalidStateTransition("This request was already answered.", details={"status": req.status})
        now = timezone.now()
        req.status = AdditionalWorkStatus.APPROVED if approve else AdditionalWorkStatus.REJECTED
        req.customer_response, req.responded_by = response, actor
        req.approved_at, req.rejected_at = (now, None) if approve else (None, now)
        req.save()
        AuditService.log(AuditAction.ADDITIONAL_WORK_RESPONDED, user=actor, organization=job_card.organization,
                         instance=req, request=request, new_data={"status": req.status, "response": response[:200]})
        JobCardService._refresh_waiting(JobCard.objects.select_for_update().get(pk=job_card.pk), actor)
        from apps.bookings import events

        events.notify_agency(job_card.booking, Event.ADDITIONAL_WORK_RESPONDED, description=req.description[:120],
                             decision="approved" if approve else "declined")
        return req

    @staticmethod
    @transaction.atomic
    def cancel_additional_work(*, work_request, actor):
        req = AdditionalWorkRequest.objects.select_for_update().get(pk=work_request.pk)
        require_job_perm(actor, req.job_card)
        if req.status != AdditionalWorkStatus.PENDING:
            raise InvalidStateTransition("Only pending requests can be withdrawn.")
        req.status = AdditionalWorkStatus.CANCELLED
        req.save(update_fields=["status", "updated_at"])
        JobCardService._refresh_waiting(JobCard.objects.select_for_update().get(pk=req.job_card_id), actor)
        return req

    @staticmethod
    @transaction.atomic
    def use_part(*, job_card, actor, part_id, quantity):
        require_job_perm(actor, job_card)
        if job_card.status not in EDITABLE:
            raise BusinessRuleViolation("Parts can't be added to a completed job card.", code="JOB_CARD_LOCKED")
        part = Part.objects.filter(pk=part_id, organization=job_card.organization).first()
        if part is None:
            raise BusinessRuleViolation("Part not found.", code="PART_NOT_FOUND", status_code=404)
        InventoryService.move(part=part, transaction_type=TransactionType.USED_IN_JOB, quantity=quantity,
                              actor=actor, job_card=job_card, reference=job_card.job_card_number)
        return JobCardPart.objects.create(job_card=job_card, part=part, quantity=Decimal(quantity),
                                          unit_price=part.selling_price, tax_rate=part.tax_rate, added_by=actor)

    @staticmethod
    @transaction.atomic
    def return_part(*, usage, actor, quantity):
        usage = JobCardPart.objects.select_for_update().select_related("job_card", "part").get(pk=usage.pk)
        require_job_perm(actor, usage.job_card)
        if usage.job_card.status not in EDITABLE:
            raise BusinessRuleViolation("Completed job cards can't be edited.", code="JOB_CARD_LOCKED")
        quantity = Decimal(quantity)
        if quantity <= 0 or quantity > usage.net_quantity:
            raise BusinessRuleViolation(f"You can return up to {usage.net_quantity}.", code="INVALID_QUANTITY")
        InventoryService.move(part=usage.part, transaction_type=TransactionType.RETURN, quantity=quantity,
                              actor=actor, job_card=usage.job_card, reference=usage.job_card.job_card_number,
                              unit_price=usage.unit_price)
        usage.returned_quantity += quantity
        usage.save(update_fields=["returned_quantity", "updated_at"])
        return usage

    @staticmethod
    @transaction.atomic
    def complete(*, job_card, actor, technician_notes=None, request=None):
        require_job_perm(actor, job_card)
        job_card = JobCard.objects.select_for_update().get(pk=job_card.pk)
        if job_card.status != J.WORK_IN_PROGRESS:
            if job_card.status == J.WAITING_APPROVAL:
                raise BusinessRuleViolation("Waiting for the customer to answer additional work requests.",
                                            code="APPROVAL_PENDING")
            raise InvalidStateTransition("Only jobs in progress can be completed.",
                                         details={"current_status": job_card.status})
        if technician_notes is not None:
            job_card.technician_notes = technician_notes
        job_card.status, job_card.completed_at = J.COMPLETED, timezone.now()
        job_card.save(update_fields=["status", "completed_at", "technician_notes", "updated_at"])
        from apps.bookings.services import BookingService

        # Booking completion triggers invoice generation and the "ready" notification.
        BookingService.transition(booking=job_card.booking, action="complete", actor=actor,
                                  note=f"Job card {job_card.job_card_number} completed", request=request)
        return job_card

    @staticmethod
    @transaction.atomic
    def close(*, job_card, actor):
        require_job_perm(actor, job_card)
        job_card = JobCard.objects.select_for_update().get(pk=job_card.pk)
        if job_card.status != J.COMPLETED:
            raise InvalidStateTransition("Only completed job cards can be closed.")
        job_card.status, job_card.closed_at = J.CLOSED, timezone.now()
        job_card.save(update_fields=["status", "closed_at", "updated_at"])
        return job_card
