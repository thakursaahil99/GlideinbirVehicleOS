from django.contrib import admin

from .models import Invoice, InvoiceItem


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 0


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "organization", "customer", "total", "amount_paid", "payment_status", "status")
    list_filter = ("status", "payment_status")
    search_fields = ("invoice_number", "customer__full_name")
    inlines = [InvoiceItemInline]
