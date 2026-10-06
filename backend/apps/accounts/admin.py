from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User

admin.site.site_header = "Glideinbir — Built by Sahil Thakur"
admin.site.site_title = "Glideinbir"


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("-date_joined",)
    list_display = ("email", "full_name", "role", "is_active", "email_verified", "date_joined")
    list_filter = ("role", "is_active", "email_verified", "is_staff")
    search_fields = ("email", "full_name", "phone")
    readonly_fields = ("date_joined", "last_login", "updated_at", "email_verified_at")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("full_name", "phone", "profile_photo")}),
        ("Access", {"fields": ("role", "is_active", "is_staff", "is_superuser", "email_verified",
                               "email_verified_at")}),
        ("Dates", {"fields": ("date_joined", "last_login", "updated_at")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "full_name", "role", "password1", "password2")}),
    )
    filter_horizontal = ()
