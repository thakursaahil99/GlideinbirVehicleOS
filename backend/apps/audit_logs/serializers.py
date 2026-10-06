from rest_framework import serializers

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True, default=None)
    organization_name = serializers.CharField(source="organization.name", read_only=True, default=None)

    class Meta:
        model = AuditLog
        fields = (
            "id", "action", "user", "user_email", "organization", "organization_name", "model_name",
            "object_id", "old_data", "new_data", "ip_address", "user_agent", "created_at",
        )
        read_only_fields = fields
