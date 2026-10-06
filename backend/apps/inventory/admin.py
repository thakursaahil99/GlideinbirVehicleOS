from django.contrib import admin

from .models import Part, StockTransaction


@admin.register(Part)
class PartAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "organization", "stock_quantity", "minimum_stock", "selling_price", "active")
    list_filter = ("active", "unit")
    search_fields = ("name", "sku")
    readonly_fields = ("stock_quantity",)


@admin.register(StockTransaction)
class StockTransactionAdmin(admin.ModelAdmin):
    list_display = ("part", "transaction_type", "quantity", "balance_after", "created_at")
    list_filter = ("transaction_type",)

    def has_change_permission(self, request, obj=None):
        return False
