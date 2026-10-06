"""Vehicle-model catalogue: showroom stock and sales (built by Sahil Thakur)."""
from django.db import transaction

from apps.audit_logs.models import AuditAction
from apps.audit_logs.services import AuditService
from apps.core.exceptions import BusinessRuleViolation

from .models import VehicleModel, VehicleSale


class VehicleCatalogService:
    @staticmethod
    @transaction.atomic
    def adjust_stock(*, vehicle_model, quantity, actor, note="", request=None):
        vm = VehicleModel.objects.select_for_update().get(pk=vehicle_model.pk)
        new_qty = vm.stock_quantity + quantity
        if new_qty < 0:
            raise BusinessRuleViolation(f"Only {vm.stock_quantity} in stock.", code="INSUFFICIENT_STOCK")
        old = vm.stock_quantity
        vm.stock_quantity = new_qty
        vm.save(update_fields=["stock_quantity", "updated_at"])
        AuditService.log(AuditAction.AGENCY_UPDATED, user=actor, organization=vm.organization, instance=vm,
                         request=request, old_data={"stock_quantity": old},
                         new_data={"stock_quantity": new_qty, "change": quantity, "note": note})
        return vm

    @staticmethod
    @transaction.atomic
    def record_sale(*, organization, data, actor, request=None):
        # Lock the model row so two sales cannot both take the last unit.
        vm = VehicleModel.objects.select_for_update().get(pk=data["vehicle_model"].pk)
        if vm.stock_quantity < 1:
            raise BusinessRuleViolation(f"{vm} is out of stock.", code="OUT_OF_STOCK")
        vm.stock_quantity -= 1
        vm.save(update_fields=["stock_quantity", "updated_at"])
        sale = VehicleSale.objects.create(organization=organization, sold_by=actor, **{**data, "vehicle_model": vm})
        AuditService.log(AuditAction.AGENCY_UPDATED, user=actor, organization=organization, instance=sale,
                         request=request, new_data={"sale": str(sale), "price": str(sale.sale_price),
                                                    "stock_left": vm.stock_quantity})
        return sale

    @staticmethod
    @transaction.atomic
    def cancel_sale(*, sale, actor, request=None):
        """Undo a wrongly entered sale: the unit goes back into stock."""
        vm = VehicleModel.objects.select_for_update().get(pk=sale.vehicle_model_id)
        vm.stock_quantity += 1
        vm.save(update_fields=["stock_quantity", "updated_at"])
        AuditService.log(AuditAction.AGENCY_UPDATED, user=actor, organization=sale.organization, instance=vm,
                         request=request, old_data={"sale": str(sale)},
                         new_data={"sale": "cancelled", "stock_quantity": vm.stock_quantity})
        sale.delete()
