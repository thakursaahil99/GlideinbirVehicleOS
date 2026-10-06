from rest_framework import serializers

from apps.vehicles.models import VehicleType

from .models import Service, VendorService


class ServiceSerializer(serializers.ModelSerializer):
    supported_vehicle_types = serializers.ListField(child=serializers.ChoiceField(choices=VehicleType.choices),
                                                    allow_empty=False)

    class Meta:
        model = Service
        fields = ("id", "name", "slug", "category", "description", "supported_vehicle_types", "default_duration",
                  "base_price", "tax", "active", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")
        extra_kwargs = {"slug": {"required": False}}

    def validate_supported_vehicle_types(self, value):
        return sorted(set(value))


class ServiceBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = ("id", "name", "slug", "category", "supported_vehicle_types", "default_duration", "base_price", "tax")
        read_only_fields = fields


class VendorServiceSerializer(serializers.ModelSerializer):
    service_detail = ServiceBriefSerializer(source="service", read_only=True)
    price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    duration = serializers.IntegerField(read_only=True)
    tax_rate = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)

    class Meta:
        model = VendorService
        fields = ("id", "service", "service_detail", "custom_price", "custom_duration", "price", "duration",
                  "tax_rate", "capacity", "required_resource_type", "active", "pickup_available", "drop_available",
                  "online_booking_enabled", "description", "created_at", "updated_at")
        read_only_fields = ("id", "service_detail", "price", "duration", "tax_rate", "created_at", "updated_at")
        validators = []  # (organization, service) uniqueness is checked in the service layer


class VendorServiceUpdateSerializer(VendorServiceSerializer):
    class Meta(VendorServiceSerializer.Meta):
        read_only_fields = (*VendorServiceSerializer.Meta.read_only_fields, "service")


class PublicVendorServiceSerializer(serializers.ModelSerializer):
    """What a customer sees when comparing workshops."""

    service = ServiceBriefSerializer(read_only=True)
    price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    duration = serializers.IntegerField(read_only=True)
    tax_rate = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)
    organization_id = serializers.UUIDField(read_only=True)
    organization_name = serializers.CharField(source="organization.name", read_only=True)

    class Meta:
        model = VendorService
        fields = ("id", "organization_id", "organization_name", "service", "price", "duration", "tax_rate",
                  "pickup_available", "drop_available", "description")
        read_only_fields = fields
