from decimal import Decimal

from django.db import transaction
from django.db.models import Max

from apps.audit_logs.models import AuditAction
from apps.audit_logs.services import AuditService
from apps.core.exceptions import BusinessRuleViolation

from .models import Part, StockTransaction, TransactionType

INBOUND = {TransactionType.PURCHASE, TransactionType.RETURN}
OUTBOUND = {TransactionType.SALE, TransactionType.USED_IN_JOB}


class InventoryService:
    @staticmethod
    @transaction.atomic
    def move(*, part, transaction_type, quantity, actor, unit_price=None, job_card=None, reference="", note="",
             request=None):
        """
        The only way stock changes. Locks the part row, applies a signed quantity and
        writes the ledger row. ADJUSTMENT takes a signed quantity; other types take a
        positive quantity and the sign comes from the type.
        """
        quantity = Decimal(quantity)
        if quantity == 0:
            raise BusinessRuleViolation("Quantity must not be zero.", code="INVALID_QUANTITY")
        if transaction_type != TransactionType.ADJUSTMENT:
            if quantity < 0:
                raise BusinessRuleViolation("Quantity must be positive.", code="INVALID_QUANTITY")
            signed = quantity if transaction_type in INBOUND else -quantity
        else:
            signed = quantity
            if not note.strip():
                raise BusinessRuleViolation("Adjustments need a note explaining why.", code="NOTE_REQUIRED")

        part = Part.objects.select_for_update().get(pk=part.pk)
        if signed < 0 and not part.active and transaction_type != TransactionType.ADJUSTMENT:
            raise BusinessRuleViolation("This part is inactive.", code="PART_INACTIVE")
        new_balance = part.stock_quantity + signed
        if new_balance < 0:
            raise BusinessRuleViolation(
                f"Only {part.stock_quantity} {part.get_unit_display().lower()} of {part.name} in stock.",
                code="INSUFFICIENT_STOCK", details={"available": str(part.stock_quantity)})
        part.stock_quantity = new_balance
        part.save(update_fields=["stock_quantity", "updated_at"])

        if unit_price is None:
            unit_price = part.purchase_price if transaction_type in (TransactionType.PURCHASE,
                                                                     TransactionType.ADJUSTMENT) else part.selling_price
        last_line = StockTransaction.objects.filter(part=part).aggregate(n=Max("line_no"))["n"] or 0
        tx = StockTransaction.objects.create(
            organization=part.organization, part=part, line_no=last_line + 1,
            transaction_type=transaction_type, quantity=signed,
            unit_price=unit_price, balance_after=new_balance, job_card=job_card, reference=reference, note=note,
            created_by=actor,
        )
        if transaction_type == TransactionType.ADJUSTMENT:
            AuditService.log(AuditAction.INVENTORY_ADJUSTED, user=actor, organization=part.organization,
                             instance=part, request=request, old_data={"stock": str(new_balance - signed)},
                             new_data={"stock": str(new_balance), "note": note})
        return tx
