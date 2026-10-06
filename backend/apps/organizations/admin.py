from django.contrib import admin

from .models import Membership, Organization


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0
    raw_id_fields = ("user", "created_by")


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "status", "verification_status", "created_at")
    list_filter = ("status", "verification_status", "city")
    search_fields = ("name", "legal_name", "email", "phone", "gst_number")
    readonly_fields = ("slug", "created_at", "updated_at", "status_changed_at")
    inlines = [MembershipInline]


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("user__email", "organization__name")
    list_select_related = ("user", "organization")
    raw_id_fields = ("user", "organization", "created_by")
