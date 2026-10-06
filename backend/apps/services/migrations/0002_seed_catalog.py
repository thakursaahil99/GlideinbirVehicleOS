"""Seed the global service catalog (idempotent; existing slugs are left untouched)."""
from decimal import Decimal

from django.db import migrations

ALL = ["CAR", "BIKE", "SCOOTER", "EV", "OTHER"]
FOUR_WHEEL = ["CAR", "EV"]

CATALOG = [
    # name, slug, category, vehicle types, duration (min), base price (INR), description
    ("General Service", "general-service", "MAINTENANCE", ["CAR", "EV"], 180, "3499",
     "Periodic maintenance: inspection, top-ups, filters and a full check-up."),
    ("Oil Change", "oil-change", "MAINTENANCE", ["CAR", "BIKE", "SCOOTER"], 45, "1499",
     "Engine oil and oil-filter replacement."),
    ("Brake Service", "brake-service", "REPAIR", ALL, 90, "1999", "Pad/shoe inspection, cleaning and replacement."),
    ("AC Service", "ac-service", "MAINTENANCE", FOUR_WHEEL, 120, "2499", "AC gas top-up, filter clean and cooling check."),
    ("Car Wash", "car-wash", "CLEANING", FOUR_WHEEL, 45, "499", "Exterior foam wash and interior vacuum."),
    ("Car Detailing", "car-detailing", "CLEANING", FOUR_WHEEL, 240, "4999",
     "Deep interior cleaning, polishing and paint protection."),
    ("Tyre Replacement", "tyre-replacement", "TYRES_WHEELS", ALL, 60, "799", "Tyre fitting (tyre cost billed separately)."),
    ("Battery Replacement", "battery-replacement", "ELECTRICAL", ALL, 30, "499",
     "Battery health check and replacement (battery billed separately)."),
    ("Wheel Alignment", "wheel-alignment", "TYRES_WHEELS", FOUR_WHEEL, 45, "699", "Computerised wheel alignment."),
    ("Wheel Balancing", "wheel-balancing", "TYRES_WHEELS", FOUR_WHEEL, 45, "599", "Dynamic wheel balancing."),
    ("Engine Diagnostics", "engine-diagnostics", "DIAGNOSTICS", ["CAR", "BIKE", "EV"], 60, "999",
     "OBD scan and fault-code report."),
    ("Bike Service", "bike-service", "MAINTENANCE", ["BIKE"], 120, "999", "Complete periodic service for motorcycles."),
    ("Scooter Service", "scooter-service", "MAINTENANCE", ["SCOOTER"], 90, "799", "Complete periodic service for scooters."),
    ("EV Service", "ev-service", "MAINTENANCE", ["EV"], 120, "1999",
     "Battery health, motor, brakes and software check for EVs."),
    ("Pickup & Drop", "pickup-drop", "ASSISTANCE", ALL, 30, "299", "Doorstep vehicle pickup and drop."),
    ("Insurance Assistance", "insurance-assistance", "ASSISTANCE", ALL, 30, "0",
     "Help with insurance claims and renewals."),
    ("Emergency Repair", "emergency-repair", "EMERGENCY", ALL, 60, "1499", "On-call breakdown assistance and repair."),
]


def seed(apps, schema_editor):
    Service = apps.get_model("services", "Service")
    for name, slug, category, types, duration, price, description in CATALOG:
        Service.objects.get_or_create(slug=slug, defaults={
            "name": name, "category": category, "supported_vehicle_types": sorted(types),
            "default_duration": duration, "base_price": Decimal(price), "tax": Decimal("18.00"),
            "description": description,
        })


class Migration(migrations.Migration):
    dependencies = [("services", "0001_initial")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
