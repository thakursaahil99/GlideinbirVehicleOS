from django.contrib import admin

from .models import AgencyCustomer, Customer, CustomerNote


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("full_name", "phone", "email", "city", "user", "owner_organization", "created_at")
    search_fields = ("full_name", "phone", "email")
    list_select_related = ("user", "owner_organization")
    raw_id_fields = ("user",)


@admin.register(AgencyCustomer)
class AgencyCustomerAdmin(admin.ModelAdmin):
    list_display = ("customer", "organization", "source", "created_at")
    list_filter = ("source",)
    list_select_related = ("customer", "organization")


@admin.register(CustomerNote)
class CustomerNoteAdmin(admin.ModelAdmin):
    list_display = ("customer", "organization", "author", "created_at")
    list_select_related = ("customer", "organization", "author")
