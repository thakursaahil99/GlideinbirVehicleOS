from django.db import transaction

from apps.audit_logs.models import AuditAction
from apps.audit_logs.services import AuditService, diff, snapshot
from apps.core.exceptions import BusinessRuleViolation

from .models import VendorService

PRICING_FIELDS = ("custom_price", "custom_duration", "capacity")
EDITABLE_FIELDS = (*PRICING_FIELDS, "required_resource_type", "active", "pickup_available", "drop_available",
                   "online_booking_enabled", "description")


class VendorServiceService:
    @staticmethod
    @transaction.atomic
    def create(*, organization, service, data, actor, request=None):
        if not service.active:
            raise BusinessRuleViolation("This catalog service is inactive.", code="SERVICE_INACTIVE")
        if VendorService.objects.filter(organization=organization, service=service).exists():
            raise BusinessRuleViolation("You already offer this service.", code="SERVICE_ALREADY_OFFERED")
        offering = VendorService.objects.create(organization=organization, service=service,
                                                **{k: v for k, v in data.items() if k in EDITABLE_FIELDS})
        AuditService.log(AuditAction.SERVICE_PRICE_CHANGED, user=actor, organization=organization, instance=offering,
                         request=request, new_data={"service": service.name, **snapshot(offering, PRICING_FIELDS)})
        return offering

    @staticmethod
    @transaction.atomic
    def update(*, offering, data, actor, request=None):
        offering = VendorService.objects.select_for_update().select_related("service").get(pk=offering.pk)
        before = snapshot(offering, PRICING_FIELDS)
        fields = [f for f in EDITABLE_FIELDS if f in data]
        for f in fields:
            setattr(offering, f, data[f])
        if fields:
            offering.save(update_fields=[*fields, "updated_at"])
        old, new = diff(before, snapshot(offering, PRICING_FIELDS))
        if new:
            # Price, duration and capacity changes are financial/operational — always audited.
            AuditService.log(AuditAction.SERVICE_PRICE_CHANGED, user=actor, organization=offering.organization,
                             instance=offering, request=request, old_data=old, new_data=new)
        return offering
