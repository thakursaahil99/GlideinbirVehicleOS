from django.contrib import admin

from .models import Part, PartCategory, PartFitment, StockTransaction, Supplier


class PartFitmentInline(admin.TabularInline):
    model = PartFitment
    extra = 0
    fields = ("vehicle_type", "brand", "model", "year_from", "year_to")


@admin.register(Part)
class PartAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "organization", "category", "stock_quantity", "minimum_stock", "selling_price",
                    "active")
    list_filter = ("active", "unit", "universal")
    search_fields = ("name", "sku", "hsn_code")
    readonly_fields = ("stock_quantity",)
    inlines = (PartFitmentInline,)


@admin.register(PartCategory)
class PartCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "organization")
    search_fields = ("name",)


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "phone", "gst_number", "active")
    list_filter = ("active",)
    search_fields = ("name", "phone", "gst_number")


@admin.register(StockTransaction)
class StockTransactionAdmin(admin.ModelAdmin):
    list_display = ("part", "transaction_type", "quantity", "balance_after", "supplier", "created_at")
    list_filter = ("transaction_type",)

    def has_change_permission(self, request, obj=None):
        return False
