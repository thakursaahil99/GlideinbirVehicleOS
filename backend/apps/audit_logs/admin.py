from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "user", "organization", "model_name", "object_id", "ip_address")
    list_filter = ("action", "model_name")
    search_fields = ("object_id", "user__email", "organization__name")
    list_select_related = ("user", "organization")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
