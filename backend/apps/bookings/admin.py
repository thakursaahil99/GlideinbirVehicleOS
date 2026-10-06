from django.contrib import admin

from .models import Booking, BookingReschedule, BookingStatusHistory


class StatusHistoryInline(admin.TabularInline):
    model = BookingStatusHistory
    extra = 0
    readonly_fields = ("from_status", "to_status", "changed_by", "note", "created_at")
    can_delete = False


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("booking_number", "organization", "customer", "start_datetime", "status", "payment_status")
    list_filter = ("status", "payment_status", "source")
    search_fields = ("booking_number", "customer__full_name", "vehicle__registration_number")
    list_select_related = ("organization", "customer")
    raw_id_fields = ("customer", "vehicle", "vendor_service", "assigned_staff", "assigned_resource", "created_by",
                     "cancelled_by")
    inlines = [StatusHistoryInline]

    def has_delete_permission(self, request, obj=None):
        return False  # bookings are cancelled, never deleted


admin.site.register(BookingReschedule)
