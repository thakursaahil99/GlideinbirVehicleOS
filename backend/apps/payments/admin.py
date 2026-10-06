from django.contrib import admin

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "organization", "customer", "amount", "method", "status", "paid_at")
    list_filter = ("status", "method")
    search_fields = ("transaction_id", "reference")

    def has_change_permission(self, request, obj=None):
        return False  # money movements go through PaymentService only
