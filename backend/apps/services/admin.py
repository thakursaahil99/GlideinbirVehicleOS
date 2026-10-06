from django.contrib import admin

from .models import Service, VendorService


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "default_duration", "base_price", "tax", "active")
    list_filter = ("category", "active")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(VendorService)
class VendorServiceAdmin(admin.ModelAdmin):
    list_display = ("service", "organization", "custom_price", "custom_duration", "capacity", "active")
    list_filter = ("active", "online_booking_enabled")
    list_select_related = ("service", "organization")
