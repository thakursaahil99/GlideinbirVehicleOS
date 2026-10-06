from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import (Count, DecimalField, Exists, ExpressionWrapper, F, Max, OuterRef, Q, Subquery,
                              Sum)
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.audit_logs.models import AuditAction
from apps.audit_logs.services import AuditService
from apps.core.exceptions import BusinessRuleViolation

from .models import Part, StockTransaction, TransactionType

INBOUND = {TransactionType.PURCHASE, TransactionType.RETURN}
OUTBOUND = {TransactionType.SALE, TransactionType.USED_IN_JOB}


class InventoryService:
    @staticmethod
    @transaction.atomic
    def move(*, part, transaction_type, quantity, actor, unit_price=None, job_card=None, supplier=None, reference="",
             note="", request=None):
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

        if supplier is not None:
            if transaction_type != TransactionType.PURCHASE:
                raise BusinessRuleViolation("A supplier can only be recorded on a purchase.",
                                            code="SUPPLIER_NOT_ALLOWED")
            if supplier.organization_id != part.organization_id:
                raise BusinessRuleViolation("Unknown supplier.", code="INVALID_SUPPLIER")

        part = Part.objects.select_for_update().get(pk=part.pk)
        if signed < 0 and not part.active and transaction_type != TransactionType.ADJUSTMENT:
            raise BusinessRuleViolation("This part is inactive.", code="PART_INACTIVE")
        new_balance = part.stock_quantity + signed
        if new_balance < 0:
            raise BusinessRuleViolation(
                f"Only {part.stock_quantity} {part.get_unit_display().lower()} of {part.name} in stock.",
                code="INSUFFICIENT_STOCK", details={"available": str(part.stock_quantity)})
        part.stock_quantity = new_balance
        update_fields = ["stock_quantity", "updated_at"]
        if supplier is not None and part.preferred_supplier_id is None:
            part.preferred_supplier = supplier  # first dealer it is bought from becomes the default
            update_fields.append("preferred_supplier")
        part.save(update_fields=update_fields)

        if unit_price is None:
            unit_price = part.purchase_price if transaction_type in (TransactionType.PURCHASE,
                                                                     TransactionType.ADJUSTMENT) else part.selling_price
        last_line = StockTransaction.objects.filter(part=part).aggregate(n=Max("line_no"))["n"] or 0
        tx = StockTransaction.objects.create(
            organization=part.organization, part=part, line_no=last_line + 1,
            transaction_type=transaction_type, quantity=signed,
            unit_price=unit_price, balance_after=new_balance, job_card=job_card, supplier=supplier, reference=reference,
            note=note, created_by=actor,
        )
        if transaction_type == TransactionType.ADJUSTMENT:
            AuditService.log(AuditAction.INVENTORY_ADJUSTED, user=actor, organization=part.organization,
                             instance=part, request=request, old_data={"stock": str(new_balance - signed)},
                             new_data={"stock": str(new_balance), "note": note})
        return tx


def fits_vehicle_q(*, brand, model="", vehicle_type="", year=None):
    """
    ``Q`` over ``Part`` matching parts that fit the described vehicle: universal parts,
    or a fitment for the same brand whose model, type and year bounds don't exclude it.
    """
    fitment = Q(fitments__brand__iexact=brand.strip())
    if model.strip():
        fitment &= Q(fitments__model="") | Q(fitments__model__iexact=model.strip())
    if vehicle_type:
        fitment &= Q(fitments__vehicle_type="") | Q(fitments__vehicle_type=vehicle_type)
    if year:
        fitment &= (Q(fitments__year_from__isnull=True) | Q(fitments__year_from__lte=year)) & (
            Q(fitments__year_to__isnull=True) | Q(fitments__year_to__gte=year))
    return Q(universal=True) | fitment


def stock_status(part):
    if part.stock_quantity <= 0:
        return "OUT_OF_STOCK"
    if part.stock_quantity <= part.minimum_stock:
        return "LOW_STOCK"
    return "IN_STOCK"


DEAD_STOCK_DAYS = 90


def money(value):
    """Decimal → "1234.50", matching how the rest of the API serialises amounts."""
    return str(Decimal(value or 0).quantize(Decimal("0.01")))


def inventory_summary(parts):
    """Stock value, re-order counts and slow movers for an already tenant-scoped ``Part`` queryset."""
    active = parts.filter(active=True)
    cost_value = ExpressionWrapper(F("stock_quantity") * F("purchase_price"), output_field=DecimalField())
    retail_value = ExpressionWrapper(F("stock_quantity") * F("selling_price"), output_field=DecimalField())
    totals = active.aggregate(
        parts=Count("id"), cost=Coalesce(Sum(cost_value), Decimal("0")),
        retail=Coalesce(Sum(retail_value), Decimal("0")),
        low=Count("id", filter=Q(stock_quantity__gt=0, stock_quantity__lte=F("minimum_stock"))),
        out=Count("id", filter=Q(stock_quantity__lte=0)),
    )
    by_category = (active.values("category__name")
                   .annotate(parts=Count("id"), value=Coalesce(Sum(cost_value), Decimal("0")))
                   .order_by("-value"))

    # Dead stock: holding stock but nothing went out (sale or job) in the last N days.
    since = timezone.now() - timedelta(days=DEAD_STOCK_DAYS)
    recent_out = StockTransaction.objects.filter(part=OuterRef("pk"), quantity__lt=0,
                                                 transaction_type__in=OUTBOUND, created_at__gte=since)
    last_out = (StockTransaction.objects.filter(part=OuterRef("pk"), quantity__lt=0, transaction_type__in=OUTBOUND)
                .order_by("-created_at").values("created_at")[:1])
    dead = (active.filter(stock_quantity__gt=0, created_at__lt=since)
            .annotate(value=cost_value, last_out_at=Subquery(last_out))
            .exclude(Exists(recent_out)).order_by("-value")[:10])

    return {
        "parts": totals["parts"],
        "stock_value_cost": money(totals["cost"]),
        "stock_value_retail": money(totals["retail"]),
        "low_stock": totals["low"],
        "out_of_stock": totals["out"],
        "by_category": [{"category": row["category__name"] or "Uncategorised", "parts": row["parts"],
                         "value": money(row["value"])} for row in by_category],
        "dead_stock_days": DEAD_STOCK_DAYS,
        "dead_stock": [{"id": p.id, "name": p.name, "sku": p.sku, "stock_quantity": str(p.stock_quantity), "unit": p.unit,
                        "value": money(p.value), "last_out_at": p.last_out_at} for p in dead],
    }
