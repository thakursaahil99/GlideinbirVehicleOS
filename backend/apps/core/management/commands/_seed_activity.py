"""
Demo activity for seed_demo_data: parts, a few weeks of completed jobs with
invoices and payments, a cancellation, and upcoming bookings in real free slots.
Written straight to the models (no notifications are sent). Fake data only.
"""
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.utils import timezone

from apps.availability.services import AvailabilityService
from apps.bookings.models import Booking, BookingSource, BookingStatus, BookingStatusHistory
from apps.core.numbering import next_number
from apps.customers.models import AgencyCustomer
from apps.inventory.models import Part, TransactionType
from apps.inventory.services import InventoryService
from apps.invoices.services import InvoiceService
from apps.job_cards.models import InspectionItem, JobCard, JobCardPart, JobCardStatus
from apps.organizations.models import organization_tz
from apps.payments.models import Payment
from apps.services.models import VendorService
from apps.vehicles.models import Vehicle

PARTS = [
    ("Engine oil 5W-30 (1L)", "OIL-5W30", "Castrol", "380", "620", "LITRE", 60, 15),
    ("Oil filter", "FLT-OIL", "Bosch", "180", "320", "PCS", 25, 8),
    ("Air filter", "FLT-AIR", "Mann", "260", "450", "PCS", 18, 6),
    ("Brake pad set", "BRK-PAD", "Brembo", "1100", "1850", "SET", 6, 4),
    ("Coolant (1L)", "CLNT-1L", "Prestone", "220", "390", "LITRE", 3, 5),
]
PAYMENT_METHODS = ["UPI", "CARD", "CASH", "UPI", "BANK_TRANSFER"]


def _local(org, day, hhmm):
    return datetime.combine(day, time(*hhmm), tzinfo=organization_tz(org))


def _offer_for(org, vehicle):
    for vs in VendorService.objects.filter(organization=org, active=True).select_related("service"):
        if vehicle.vehicle_type in vs.service.supported_vehicle_types:
            return vs
    return None


def seed_activity(org, technician, actor):
    if Booking.objects.filter(organization=org).exists():
        return 0
    parts = []
    for name, sku, brand, buy, sell, unit, qty, minimum in PARTS:
        part, created = Part.objects.get_or_create(
            organization=org, sku=sku,
            defaults={"name": name, "brand": brand, "purchase_price": Decimal(buy), "selling_price": Decimal(sell),
                      "unit": unit, "minimum_stock": minimum})
        if created:
            InventoryService.move(part=part, transaction_type=TransactionType.PURCHASE, quantity=qty, actor=actor,
                                  reference="Opening stock")
        parts.append(part)

    customers = [link.customer for link in AgencyCustomer.objects.filter(organization=org).select_related("customer")]
    vehicles = [v for c in customers for v in Vehicle.objects.filter(customer=c, is_active=True)]
    today = timezone.localdate()
    created = 0
    for i, vehicle in enumerate(vehicles):
        vs = _offer_for(org, vehicle)
        if vs is None:
            continue
        day = today - timedelta(days=2 + (i * 3) % 24)
        if day.weekday() == 6:
            day -= timedelta(days=1)
        start = _local(org, day, (10 if i % 2 else 14, 0))
        cancelled = i % 7 == 3
        booking = Booking.objects.create(
            organization=org, booking_number=next_number("BK"), customer=vehicle.customer, vehicle=vehicle,
            vendor_service=vs, booking_date=day, start_datetime=start,
            end_datetime=start + timedelta(minutes=vs.duration),
            status=BookingStatus.CANCELLED if cancelled else BookingStatus.COMPLETED, source=BookingSource.ONLINE,
            assigned_staff=None if cancelled else technician, quoted_price=vs.price, tax_rate=vs.tax_rate,
            duration_minutes=vs.duration, created_by=vehicle.customer.user,
            cancellation_reason="Customer travelling" if cancelled else "",
            cancelled_at=start - timedelta(days=1) if cancelled else None,
            completed_at=None if cancelled else start + timedelta(minutes=vs.duration),
        )
        flow = ["PENDING", "CANCELLED"] if cancelled else ["PENDING", "CONFIRMED", "ASSIGNED", "VEHICLE_RECEIVED",
                                                            "IN_PROGRESS", "COMPLETED"]
        prev = ""
        for status in flow:
            BookingStatusHistory.objects.create(booking=booking, from_status=prev, to_status=status,
                                                changed_by=actor)
            prev = status
        created += 1
        if cancelled:
            continue
        job = JobCard.objects.create(
            organization=org, booking=booking, vehicle=vehicle, customer=vehicle.customer,
            job_card_number=next_number("JOB"), status=JobCardStatus.CLOSED, odometer=vehicle.odometer,
            fuel_level="HALF", technician_notes="Routine service completed.", completed_at=booking.completed_at,
            closed_at=booking.completed_at)
        for area in ("EXTERIOR", "TYRES", "BRAKES", "ENGINE"):
            InspectionItem.objects.create(job_card=job, area=area, result="OK", inspected_by=technician)
        part = parts[i % 3]  # oil / filters, keep brake pads and coolant low for the re-order list
        if part.stock_quantity >= 1:
            InventoryService.move(part=part, transaction_type=TransactionType.USED_IN_JOB, quantity=1,
                                  actor=technician, job_card=job, reference=job.job_card_number)
            JobCardPart.objects.create(job_card=job, part=part, quantity=1, unit_price=part.selling_price,
                                       tax_rate=part.tax_rate, added_by=technician)
            part.refresh_from_db()
        invoice = InvoiceService.generate_for_booking(booking, actor=actor, notify=False)
        if i % 5 != 4:  # leave a few unpaid for the pending-payments report
            Payment.objects.create(organization=org, invoice=invoice, booking=booking, customer=vehicle.customer,
                                   amount=invoice.total, method=PAYMENT_METHODS[i % 5], status="SUCCEEDED",
                                   gateway="mock" if PAYMENT_METHODS[i % 5] in ("UPI", "CARD") else "offline",
                                   transaction_id=f"seed_{invoice.invoice_number}",
                                   paid_at=booking.completed_at + timedelta(hours=1), created_by=actor)
            InvoiceService.refresh_payment_status(invoice)

    # Upcoming bookings in genuinely free slots.
    for j, vehicle in enumerate(vehicles[:6]):
        vs = _offer_for(org, vehicle)
        if vs is None:
            continue
        availability = AvailabilityService(vs)
        for offset in range(1 + j, 10 + j):
            day = today + timedelta(days=offset)
            slots = [s for s in availability.get_slots(day) if s.available]
            if slots:
                slot = slots[j % len(slots)]
                status = BookingStatus.CONFIRMED if j % 2 else BookingStatus.PENDING
                booking = Booking.objects.create(
                    organization=org, booking_number=next_number("BK"), customer=vehicle.customer, vehicle=vehicle,
                    vendor_service=vs, booking_date=day, start_datetime=slot.start, end_datetime=slot.end,
                    status=status, assigned_resource_id=slot.free_resource_ids[0] if slot.free_resource_ids else None,
                    quoted_price=vs.price, tax_rate=vs.tax_rate, duration_minutes=vs.duration,
                    created_by=vehicle.customer.user, confirmed_at=timezone.now() if j % 2 else None,
                )
                BookingStatusHistory.objects.create(booking=booking, to_status="PENDING", changed_by=actor)
                if status == BookingStatus.CONFIRMED:
                    BookingStatusHistory.objects.create(booking=booking, from_status="PENDING",
                                                        to_status="CONFIRMED", changed_by=actor)
                created += 1
                break
    return created
