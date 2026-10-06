from django.contrib import admin

from .models import Vehicle, VehicleDocument


class VehicleDocumentInline(admin.TabularInline):
    model = VehicleDocument
    extra = 0


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ("registration_number", "brand", "model", "vehicle_type", "customer", "is_active")
    list_filter = ("vehicle_type", "fuel_type", "is_active")
    search_fields = ("registration_number", "vin", "brand", "model", "customer__full_name")
    list_select_related = ("customer",)
    inlines = [VehicleDocumentInline]
