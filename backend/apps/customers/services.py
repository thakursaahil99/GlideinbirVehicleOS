from django.db import transaction

from apps.audit_logs.models import AuditAction
from apps.audit_logs.services import AuditService, diff, snapshot
from apps.core.exceptions import BusinessRuleViolation
from apps.core.tenancy import get_user_organization_id

from .models import AgencyCustomer, Customer, CustomerNote, CustomerSource

PROFILE_FIELDS = ("full_name", "phone", "email", "address", "city", "state", "country", "pincode", "notes")


class CustomerService:
    @staticmethod
    def ensure_profile(user):
        """Every CUSTOMER user has exactly one Customer profile."""
        customer, created = Customer.objects.get_or_create(
            user=user, defaults={"full_name": user.full_name, "phone": user.phone, "email": user.email}
        )
        return customer

    @staticmethod
    def sync_from_user(user):
        Customer.objects.filter(user=user).update(full_name=user.full_name, phone=user.phone, email=user.email)

    @staticmethod
    def link_to_agency(customer, organization, source=CustomerSource.BOOKING):
        link, _ = AgencyCustomer.objects.get_or_create(organization=organization, customer=customer,
                                                       defaults={"source": source})
        return link

    @staticmethod
    @transaction.atomic
    def create_walk_in(*, organization, actor, data, request=None):
        customer = Customer.objects.create(owner_organization=organization,
                                           **{k: v for k, v in data.items() if k in PROFILE_FIELDS})
        CustomerService.link_to_agency(customer, organization, CustomerSource.WALK_IN)
        AuditService.log(AuditAction.CUSTOMER_CREATED, user=actor, organization=organization, instance=customer,
                         request=request, new_data=snapshot(customer, ["full_name", "phone", "email", "city"]))
        return customer

    @staticmethod
    def can_edit_identity(customer, user):
        """Customers edit themselves; an agency edits only walk-ins it created; Super Admin edits anyone."""
        if user.is_super_admin:
            return True
        if user.is_customer:
            return customer.user_id == user.pk
        return customer.user_id is None and customer.owner_organization_id == get_user_organization_id(user)

    @staticmethod
    @transaction.atomic
    def update_profile(*, customer, data, actor, organization=None, request=None):
        if not CustomerService.can_edit_identity(customer, actor):
            raise BusinessRuleViolation(
                "This customer manages their own profile. Add an internal note instead.",
                code="CUSTOMER_SELF_MANAGED", status_code=403,
            )
        fields = [f for f in PROFILE_FIELDS if f in data]
        before = snapshot(customer, fields)
        for f in fields:
            setattr(customer, f, data[f])
        if fields:
            customer.save(update_fields=[*fields, "updated_at"])
            # Keep the login account in sync for self-managed customers.
            if customer.user_id and any(f in fields for f in ("full_name", "phone")):
                user = customer.user
                user.full_name, user.phone = customer.full_name, customer.phone
                user.save(update_fields=["full_name", "phone", "updated_at"])
            old, new = diff(before, snapshot(customer, fields))
            if new:
                AuditService.log(AuditAction.CUSTOMER_UPDATED, user=actor, organization=organization,
                                 instance=customer, request=request, old_data=old, new_data=new)
        return customer

    @staticmethod
    def add_note(*, customer, organization, author, body):
        return CustomerNote.objects.create(customer=customer, organization=organization, author=author, body=body)
