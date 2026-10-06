"""
Side effects of booking lifecycle changes (notifications; payments are added by
the payments app). Everything external runs after the transaction commits.
"""
from django.db import transaction

from apps.accounts.constants import Role
from apps.notifications.models import Event
from apps.notifications.services import NotificationService
from apps.organizations.models import organization_tz


def _when(booking):
    local = booking.start_datetime.astimezone(organization_tz(booking.organization))
    return local.strftime("%a %d %b %Y, %I:%M %p")


def context(booking, **extra):
    return {
        "booking_number": booking.booking_number,
        "service": booking.vendor_service.service.name,
        "agency": booking.organization.name,
        "vehicle": f"{booking.vehicle.brand} {booking.vehicle.model} ({booking.vehicle.registration_number})",
        "customer": booking.customer.full_name,
        "when": _when(booking),
        **extra,
    }


def _data(booking):
    return {"booking_id": str(booking.pk), "booking_number": booking.booking_number}


def notify_customer(booking, event, **extra):
    customer = booking.customer
    users = [customer.user] if customer.user_id else []
    contacts = [] if customer.user_id else [(customer.email, customer.phone)]
    return NotificationService.notify(event, users=users, contacts=contacts, organization=booking.organization,
                                      context=context(booking, **extra), data=_data(booking))


def notify_agency(booking, event, **extra):
    from apps.organizations.models import Membership

    managers = [m.user for m in Membership.objects.filter(
        organization=booking.organization, is_active=True,
        user__role__in=[Role.AGENCY_ADMIN, Role.AGENCY_MANAGER]).select_related("user")]
    if booking.assigned_staff_id:
        managers.append(booking.assigned_staff)
    return NotificationService.notify(event, users=managers, organization=booking.organization,
                                      context=context(booking, **extra), data=_data(booking))


def booking_created(booking, agency_settings):
    notify_customer(booking, Event.BOOKING_CONFIRMED if booking.status == "CONFIRMED" else Event.BOOKING_CREATED)
    notify_agency(booking, Event.NEW_BOOKING_FOR_AGENCY)
    if agency_settings.require_online_payment:
        from apps.payments.services import PaymentService

        PaymentService.create_booking_payment(booking)


STATUS_EVENTS = {
    "confirm": Event.BOOKING_CONFIRMED,
    "reject": Event.BOOKING_REJECTED,
    "receive_vehicle": Event.VEHICLE_RECEIVED,
    "start": Event.SERVICE_STARTED,
    "complete": Event.SERVICE_COMPLETED,
}


def _sync_job_card(booking, action):
    """Keep the job card in step when staff drive the lifecycle from the booking screen."""
    from django.utils import timezone

    from apps.core.exceptions import BusinessRuleViolation
    from apps.job_cards.models import AdditionalWorkStatus, JobCard, JobCardStatus
    from apps.job_cards.services import JobCardService

    if action == "receive_vehicle":
        JobCardService.open_for_booking(booking)
        return
    job_card = JobCard.objects.filter(booking=booking).first()
    if job_card is None:
        return
    if action == "start" and job_card.status in (JobCardStatus.OPEN, JobCardStatus.INSPECTION):
        job_card.status = JobCardStatus.WORK_IN_PROGRESS
        job_card.save(update_fields=["status", "updated_at"])
    if action == "complete":
        if job_card.additional_work.filter(status=AdditionalWorkStatus.PENDING).exists():
            raise BusinessRuleViolation("Waiting for the customer to answer additional work requests.",
                                        code="APPROVAL_PENDING")
        if job_card.status not in (JobCardStatus.COMPLETED, JobCardStatus.CLOSED):
            job_card.status, job_card.completed_at = JobCardStatus.COMPLETED, timezone.now()
            job_card.save(update_fields=["status", "completed_at", "updated_at"])


def booking_status_changed(booking, previous, action):
    _sync_job_card(booking, action)
    if action == "complete":
        from apps.invoices.services import InvoiceService

        transaction.on_commit(lambda: InvoiceService.generate_for_booking_async(booking.pk))
    event = STATUS_EVENTS.get(action)
    if event:
        notify_customer(booking, event, reason=booking.cancellation_reason)


def booking_cancelled(booking, actor):
    notify_customer(booking, Event.BOOKING_CANCELLED, reason=booking.cancellation_reason)
    if actor.is_customer:
        notify_agency(booking, Event.BOOKING_CANCELLED, reason=booking.cancellation_reason)


def booking_rescheduled(booking, history):
    notify_customer(booking, Event.BOOKING_RESCHEDULED)
    notify_agency(booking, Event.BOOKING_RESCHEDULED)
