"""Global search across the entities the user is allowed to see (tenant-scoped)."""
from django.db.models import Q

from apps.bookings.models import Booking
from apps.customers.models import Customer
from apps.invoices.models import Invoice
from apps.job_cards.models import JobCard
from apps.organizations.models import Organization
from apps.vehicles.models import Vehicle, normalize_registration

LIMIT = 6


def global_search(user, q):
    q = q.strip()
    reg = normalize_registration(q)
    results = {}

    if not user.is_customer:
        customers = Customer.objects.for_user(user).filter(
            Q(full_name__icontains=q) | Q(phone__icontains=q) | Q(email__icontains=q)).distinct()[:LIMIT]
        results["customers"] = [{"id": str(c.pk), "title": c.full_name, "subtitle": c.phone or c.email}
                                for c in customers]

    vehicle_q = Q(vin__iexact=q.upper()) | Q(brand__icontains=q) | Q(model__icontains=q)
    if len(reg) >= 3:
        vehicle_q |= Q(registration_number__icontains=reg)
    vehicles = Vehicle.objects.for_user(user).filter(vehicle_q).select_related("customer").distinct()[:LIMIT]
    results["vehicles"] = [{"id": str(v.pk), "title": v.registration_number,
                            "subtitle": f"{v.brand} {v.model} · {v.customer.full_name}"} for v in vehicles]

    bookings = Booking.objects.for_user(user).filter(
        Q(booking_number__icontains=q) | Q(customer__full_name__icontains=q)
        | (Q(vehicle__registration_number__icontains=reg) if len(reg) >= 3 else Q(pk__in=[]))
    ).select_related("customer", "vendor_service__service").order_by("-start_datetime")[:LIMIT]
    results["bookings"] = [{"id": str(b.pk), "title": b.booking_number,
                            "subtitle": f"{b.vendor_service.service.name} · {b.customer.full_name}",
                            "status": b.status} for b in bookings]

    invoices = Invoice.objects.for_user(user).filter(
        Q(invoice_number__icontains=q) | Q(customer__full_name__icontains=q)).select_related("customer")[:LIMIT]
    results["invoices"] = [{"id": str(i.pk), "title": i.invoice_number, "subtitle": i.customer.full_name,
                            "status": i.payment_status} for i in invoices]

    jobs = JobCard.objects.for_user(user).filter(
        Q(job_card_number__icontains=q) | (Q(vehicle__registration_number__icontains=reg) if len(reg) >= 3
                                           else Q(pk__in=[]))).select_related("vehicle")[:LIMIT]
    results["job_cards"] = [{"id": str(j.pk), "title": j.job_card_number, "subtitle": j.vehicle.registration_number,
                             "status": j.status} for j in jobs]

    vendor_qs = Organization.objects.all() if user.is_super_admin else Organization.objects.bookable()
    vendors = vendor_qs.filter(Q(name__icontains=q) | Q(city__icontains=q))[:LIMIT]
    results["vendors"] = [{"id": str(o.pk), "title": o.name, "subtitle": o.city, "status": o.status}
                          for o in vendors]
    return results
