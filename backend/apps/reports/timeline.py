"""
Customer timeline: booking created → confirmed → vehicle received → inspection →
additional work requested / answered → service completed → invoice → payment.

Agencies only see events that belong to their own agency.
"""
from apps.bookings.models import BookingReschedule, BookingStatusHistory
from apps.invoices.models import Invoice
from apps.job_cards.models import AdditionalWorkRequest, InspectionItem
from apps.payments.models import Payment

STATUS_TITLES = {
    "PENDING": "Booking created", "CONFIRMED": "Booking confirmed", "ASSIGNED": "Technician assigned",
    "VEHICLE_RECEIVED": "Vehicle received", "IN_PROGRESS": "Service in progress",
    "WAITING_FOR_APPROVAL": "Waiting for approval", "COMPLETED": "Service completed",
    "CANCELLED": "Booking cancelled", "REJECTED": "Booking rejected", "NO_SHOW": "Marked as no-show",
}


def customer_timeline(customer, organization_id=None, limit=200):
    def scoped(qs, field):
        return qs.filter(**{field: organization_id}) if organization_id else qs

    events = []
    for h in scoped(BookingStatusHistory.objects.filter(booking__customer=customer),
                    "booking__organization_id").select_related("booking__vendor_service__service",
                                                               "booking__organization"):
        events.append({"at": h.created_at, "type": f"BOOKING_{h.to_status}",
                       "title": STATUS_TITLES.get(h.to_status, h.to_status),
                       "detail": f"{h.booking.booking_number} · {h.booking.vendor_service.service.name}"
                                 + (f" — {h.note}" if h.note and h.to_status in ("CANCELLED", "REJECTED") else ""),
                       "agency": h.booking.organization.name, "ref": str(h.booking_id)})
    for r in scoped(BookingReschedule.objects.filter(booking__customer=customer), "booking__organization_id") \
            .select_related("booking__organization"):
        events.append({"at": r.created_at, "type": "BOOKING_RESCHEDULED", "title": "Booking rescheduled",
                       "detail": f"{r.booking.booking_number} moved to {r.new_start:%d %b %Y %H:%M}",
                       "agency": r.booking.organization.name, "ref": str(r.booking_id)})
    inspected = {}
    for item in scoped(InspectionItem.objects.filter(job_card__customer=customer), "job_card__organization_id") \
            .select_related("job_card__organization"):
        key = item.job_card_id
        if key not in inspected or item.created_at < inspected[key]["at"]:
            inspected[key] = {"at": item.created_at, "type": "INSPECTION_COMPLETED", "title": "Inspection recorded",
                              "detail": item.job_card.job_card_number, "agency": item.job_card.organization.name,
                              "ref": str(item.job_card_id)}
    events += inspected.values()
    for w in scoped(AdditionalWorkRequest.objects.filter(job_card__customer=customer), "job_card__organization_id") \
            .select_related("job_card__organization"):
        events.append({"at": w.created_at, "type": "ADDITIONAL_WORK_REQUESTED", "title": "Additional work requested",
                       "detail": f"{w.description[:80]} (₹{w.estimated_cost:,.2f})",
                       "agency": w.job_card.organization.name, "ref": str(w.job_card_id)})
        if w.approved_at or w.rejected_at:
            events.append({"at": w.approved_at or w.rejected_at, "type": f"ADDITIONAL_WORK_{w.status}",
                           "title": "Customer approved extra work" if w.approved_at else "Customer declined extra work",
                           "detail": w.description[:80], "agency": w.job_card.organization.name,
                           "ref": str(w.job_card_id)})
    for inv in scoped(Invoice.objects.filter(customer=customer).exclude(status="DRAFT"), "organization_id") \
            .select_related("organization"):
        events.append({"at": inv.issued_at or inv.created_at, "type": "INVOICE_GENERATED",
                       "title": "Invoice generated", "detail": f"{inv.invoice_number} · ₹{inv.total:,.2f}",
                       "agency": inv.organization.name, "ref": str(inv.pk)})
    for p in scoped(Payment.objects.settled().filter(customer=customer), "organization_id") \
            .select_related("organization"):
        events.append({"at": p.paid_at or p.created_at, "type": "PAYMENT_RECEIVED", "title": "Payment received",
                       "detail": f"₹{p.amount:,.2f} via {p.get_method_display()}", "agency": p.organization.name,
                       "ref": str(p.pk)})
    events.sort(key=lambda e: e["at"], reverse=True)
    return [{**e, "at": e["at"].isoformat()} for e in events[:limit]]
