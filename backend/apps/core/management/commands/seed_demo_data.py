"""
python manage.py seed_demo_data

Seeds: 1 Super Admin, 3 agencies (Admin + Manager + Technician each), 20 customers with vehicles,
working hours, resources, priced services, parts, past jobs with invoices and payments, and
upcoming bookings. Idempotent — safe to run repeatedly. Fake data only.
"""
from datetime import date, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.constants import DEFAULT_MANAGER_PERMISSIONS, DEFAULT_STAFF_PERMISSIONS, Role
from apps.accounts.models import User
from apps.customers.services import CustomerService

from ._seed_activity import seed_activity
from apps.organizations.models import Membership, Organization, OrganizationStatus, VerificationStatus
from apps.services.models import Service, VendorService
from apps.vehicles.models import FuelType, Vehicle, VehicleType
from apps.vendors.models import Holiday, ResourceType, ServiceResource, WorkingHours
from apps.vendors.services import get_agency_settings

AGENCIES = [
    {"name": "Speedy Auto Care", "city": "Mumbai", "state": "Maharashtra", "phone": "+912240000001",
     "slug": "speedy-auto-care", "status": OrganizationStatus.ACTIVE,
     # (catalog slug, custom price or None, capacity, reserves a bay?)
     "offers": [("general-service", "3299", 2, True), ("oil-change", None, 2, True), ("car-wash", "449", 3, False),
                ("ac-service", None, 1, True), ("wheel-alignment", "649", 1, True), ("pickup-drop", None, 2, False),
                ("engine-diagnostics", None, 1, False)]},
    {"name": "GreenVolt EV Service", "city": "Bengaluru", "state": "Karnataka", "phone": "+918040000002",
     "slug": "greenvolt-ev-service", "status": OrganizationStatus.ACTIVE,
     "offers": [("ev-service", "1799", 2, True), ("battery-replacement", None, 1, False),
                ("general-service", "3599", 1, True), ("engine-diagnostics", "899", 1, False),
                ("oil-change", "1399", 1, True)]},
    {"name": "Royal Bikes Workshop", "city": "Chandigarh", "state": "Punjab", "phone": "+911724000003",
     "slug": "royal-bikes-workshop", "status": OrganizationStatus.PENDING,
     "offers": [("bike-service", None, 2, False), ("scooter-service", "699", 2, False), ("oil-change", "599", 2, False)]},
]

FIRST_NAMES = ["Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh", "Ayaan", "Krishna", "Ishaan",
               "Ananya", "Diya", "Saanvi", "Aadhya", "Kavya", "Pari", "Myra", "Anika", "Navya", "Riya"]
LAST_NAMES = ["Sharma", "Verma", "Patel", "Reddy", "Nair", "Gupta", "Singh", "Iyer", "Mehta", "Kapoor"]
CITIES = ["Mumbai", "Pune", "Bengaluru", "Delhi", "Chandigarh"]
VEHICLES = [
    ("Maruti Suzuki", "Swift", VehicleType.CAR, FuelType.PETROL),
    ("Hyundai", "Creta", VehicleType.CAR, FuelType.DIESEL),
    ("Tata", "Nexon EV", VehicleType.EV, FuelType.ELECTRIC),
    ("Royal Enfield", "Classic 350", VehicleType.BIKE, FuelType.PETROL),
    ("Honda", "Activa 6G", VehicleType.SCOOTER, FuelType.PETROL),
    ("Ather", "450X", VehicleType.EV, FuelType.ELECTRIC),
    ("Mahindra", "XUV700", VehicleType.CAR, FuelType.DIESEL),
]


class Command(BaseCommand):
    help = "Seed the database with fake demo data (development only)."

    def add_arguments(self, parser):
        parser.add_argument("--password", default="Demo@12345", help="Password for every demo account.")
        parser.add_argument("--force", action="store_true", help="Allow running with DEBUG=False.")

    def _user(self, email, full_name, role, password, **extra):
        user, created = User.objects.get_or_create(
            email=email, defaults={"full_name": full_name, "role": role, "email_verified": True, **extra}
        )
        if created:
            user.set_password(password)
            user.save(update_fields=["password"])
        return user

    def _seed_operations(self, org, technician):
        """Phase 2: Mon–Sat split shifts, two bays, one technician, a sample holiday."""
        get_agency_settings(org)
        if not WorkingHours.objects.filter(organization=org).exists():
            WorkingHours.objects.bulk_create(
                [WorkingHours(organization=org, weekday=d, opens_at=time(9), closes_at=time(13)) for d in range(6)]
                + [WorkingHours(organization=org, weekday=d, opens_at=time(14), closes_at=time(19)) for d in range(6)]
            )
        for name, rtype, staff in (("Bay 1", ResourceType.BAY, None), ("Bay 2", ResourceType.BAY, None),
                                   (f"Technician — {technician.full_name}", ResourceType.TECHNICIAN, technician)):
            ServiceResource.objects.get_or_create(organization=org, name=name,
                                                  defaults={"resource_type": rtype, "staff": staff})
        Holiday.objects.get_or_create(organization=org, name="Republic Day",
                                      defaults={"start_date": date(timezone.localdate().year + 1, 1, 26),
                                                "end_date": date(timezone.localdate().year + 1, 1, 26)})

    def _seed_offers(self, org, offers):
        """Phase 4: the agency's priced service offerings."""
        for slug, price, capacity, needs_bay in offers:
            VendorService.objects.get_or_create(
                organization=org, service=Service.objects.get(slug=slug),
                defaults={"custom_price": Decimal(price) if price else None, "capacity": capacity,
                          "required_resource_type": ResourceType.BAY if needs_bay else "",
                          "pickup_available": slug in ("general-service", "ev-service"), "drop_available": True},
            )

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError("Refusing to seed demo data with DEBUG=False. Pass --force if you are sure.")
        password = options["password"]

        self._user("superadmin@demo.local", "Platform Super Admin", Role.SUPER_ADMIN, password,
                   is_staff=True, is_superuser=True)

        for i, spec in enumerate(AGENCIES, start=1):
            org, _ = Organization.objects.get_or_create(
                slug=spec["slug"],
                defaults={
                    "name": spec["name"], "legal_name": f"{spec['name']} Pvt Ltd", "phone": spec["phone"],
                    "email": f"contact@{spec['slug']}.demo.local", "city": spec["city"], "state": spec["state"],
                    "country": "India", "pincode": f"{400000 + i:06d}", "address": f"{i} Demo Industrial Area",
                    "status": spec["status"],
                    "verification_status": (VerificationStatus.VERIFIED if spec["status"] == OrganizationStatus.ACTIVE
                                            else VerificationStatus.PENDING),
                    "description": "Demo agency created by seed_demo_data.",
                },
            )
            staff = [
                (f"admin@{spec['slug']}.demo.local", f"{spec['name']} Admin", Role.AGENCY_ADMIN, []),
                (f"manager@{spec['slug']}.demo.local", f"{spec['name']} Manager", Role.AGENCY_MANAGER,
                 DEFAULT_MANAGER_PERMISSIONS),
                (f"staff@{spec['slug']}.demo.local", f"{spec['name']} Technician", Role.AGENCY_STAFF,
                 DEFAULT_STAFF_PERMISSIONS),
            ]
            members = {}
            for email, name, role, perms in staff:
                user = self._user(email, name, role, password)
                members[role] = user
                Membership.objects.get_or_create(
                    user=user, organization=org, defaults={"permissions": [str(p) for p in perms]}
                )
            self._seed_operations(org, technician=members[Role.AGENCY_STAFF])
            self._seed_offers(org, spec["offers"])

        orgs = list(Organization.objects.filter(slug__in=[a["slug"] for a in AGENCIES]).order_by("name"))
        active_orgs = [o for o in orgs if o.status == OrganizationStatus.ACTIVE]
        for n in range(20):
            first, last = FIRST_NAMES[n], LAST_NAMES[n % len(LAST_NAMES)]
            user = self._user(f"customer{n + 1:02d}@demo.local", f"{first} {last}", Role.CUSTOMER, password,
                              phone=f"+9198{n + 1:08d}")
            profile = CustomerService.ensure_profile(user)
            if not profile.city:
                profile.city = CITIES[n % len(CITIES)]
                profile.save(update_fields=["city"])
            CustomerService.link_to_agency(profile, active_orgs[n % len(active_orgs)])
            for v in range(1 + n % 3):
                brand, model, vtype, fuel = VEHICLES[(n + v) % len(VEHICLES)]
                Vehicle.objects.get_or_create(
                    customer=profile, registration_number=f"MH{12 + v:02d}DM{n + 1:02d}{v + 1:02d}",
                    defaults={"vehicle_type": vtype, "brand": brand, "model": model, "fuel_type": fuel,
                              "manufacturing_year": 2016 + (n + v) % 9, "odometer": 5000 + 3700 * n,
                              "insurance_expiry": timezone.localdate() + timedelta(days=20 + 30 * v)},
                )

        admin_users = {o.pk: Membership.objects.filter(organization=o, user__role=Role.AGENCY_ADMIN).first().user
                       for o in active_orgs}
        for org in active_orgs:
            technician = Membership.objects.filter(organization=org, user__role=Role.AGENCY_STAFF).first().user
            made = seed_activity(org, technician, admin_users[org.pk])
            if made:
                self.stdout.write(f"  {org.name}: {made} bookings with job cards, invoices and payments")

        self.stdout.write(self.style.SUCCESS("Demo data ready."))
        self.stdout.write(f"  Super Admin : superadmin@demo.local / {password}")
        self.stdout.write(f"  Agency Admin: admin@speedy-auto-care.demo.local / {password}")
        self.stdout.write(f"  Staff       : staff@speedy-auto-care.demo.local / {password}")
        self.stdout.write(f"  Customer    : customer01@demo.local / {password}")
        self.stdout.write("  (Royal Bikes Workshop is left PENDING so you can try the approval flow.)")
