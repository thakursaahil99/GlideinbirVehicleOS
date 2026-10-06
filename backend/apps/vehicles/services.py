from django.db import transaction

from apps.audit_logs.models import AuditAction
from apps.audit_logs.services import AuditService, diff, snapshot
from apps.core.exceptions import BusinessRuleViolation
from apps.core.tenancy import get_user_organization, get_user_organization_id
from apps.customers.models import Customer

from .models import Vehicle, normalize_registration

EDITABLE_FIELDS = (
    "vehicle_type", "brand", "model", "variant", "registration_number", "vin", "chassis_number", "engine_number",
    "fuel_type", "manufacturing_year", "color", "odometer", "insurance_expiry", "registration_expiry",
    "pollution_expiry", "notes",
)
AUDIT_FIELDS = ["vehicle_type", "brand", "model", "registration_number", "vin", "odometer"]


class VehicleService:
    @staticmethod
    def resolve_owner(*, actor, customer_id=None):
        """
        Customers always add vehicles to themselves. Agency users must name a
        customer linked to their agency — otherwise 'not found', never 'forbidden',
        so other tenants' customers cannot be probed.
        """
        if actor.is_customer:
            return Customer.objects.get(user=actor)
        if customer_id is None:
            raise BusinessRuleViolation("customer is required.", code="CUSTOMER_REQUIRED")
        customer = Customer.objects.for_user(actor).filter(pk=customer_id).first()
        if customer is None:
            raise BusinessRuleViolation("Customer not found.", code="CUSTOMER_NOT_FOUND", status_code=404)
        return customer

    @staticmethod
    def can_edit(vehicle, user):
        if user.is_super_admin:
            return True
        if user.is_customer:
            return vehicle.customer.user_id == user.pk
        customer = vehicle.customer
        return customer.user_id is None and customer.owner_organization_id == get_user_organization_id(user)

    @staticmethod
    def _check_duplicate(customer, registration_number, exclude_pk=None):
        reg = normalize_registration(registration_number)
        qs = Vehicle.objects.filter(customer=customer, registration_number=reg, is_active=True)
        if exclude_pk:
            qs = qs.exclude(pk=exclude_pk)
        if qs.exists():
            raise BusinessRuleViolation("This vehicle is already registered.", code="DUPLICATE_VEHICLE",
                                        details={"registration_number": ["Already registered for this customer."]})

    @staticmethod
    @transaction.atomic
    def create(*, actor, customer, data, request=None):
        VehicleService._check_duplicate(customer, data["registration_number"])
        vehicle = Vehicle.objects.create(customer=customer, **{k: v for k, v in data.items() if k in EDITABLE_FIELDS})
        organization = None if actor.is_customer else get_user_organization(actor)
        AuditService.log(AuditAction.VEHICLE_CREATED, user=actor, organization=organization, instance=vehicle,
                         request=request, new_data=snapshot(vehicle, AUDIT_FIELDS))
        return vehicle

    @staticmethod
    @transaction.atomic
    def update(*, vehicle, actor, data, request=None):
        if not VehicleService.can_edit(vehicle, actor):
            raise BusinessRuleViolation("Only the owner can edit this vehicle.", code="VEHICLE_SELF_MANAGED",
                                        status_code=403)
        if "registration_number" in data:
            VehicleService._check_duplicate(vehicle.customer, data["registration_number"], exclude_pk=vehicle.pk)
        fields = [f for f in EDITABLE_FIELDS if f in data]
        before = snapshot(vehicle, AUDIT_FIELDS)
        for f in fields:
            setattr(vehicle, f, data[f])
        vehicle.save()
        old, new = diff(before, snapshot(vehicle, AUDIT_FIELDS))
        if new:
            AuditService.log(AuditAction.VEHICLE_UPDATED, user=actor,
                             organization=None if actor.is_customer else get_user_organization(actor),
                             instance=vehicle, request=request, old_data=old, new_data=new)
        return vehicle

    @staticmethod
    @transaction.atomic
    def archive(*, vehicle, actor, request=None):
        """Vehicles are archived, never deleted, so service history stays intact."""
        if not VehicleService.can_edit(vehicle, actor):
            raise BusinessRuleViolation("Only the owner can archive this vehicle.", code="VEHICLE_SELF_MANAGED",
                                        status_code=403)
        vehicle.is_active = False
        vehicle.save(update_fields=["is_active", "updated_at"])
        AuditService.log(AuditAction.VEHICLE_ARCHIVED, user=actor, instance=vehicle, request=request,
                         organization=None if actor.is_customer else get_user_organization(actor))
        return vehicle
