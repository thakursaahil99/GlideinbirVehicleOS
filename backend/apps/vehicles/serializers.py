from django.utils import timezone
from rest_framework import serializers

from .models import Vehicle, VehicleDocument, VehicleType, normalize_registration


class VehicleSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.full_name", read_only=True)
    customer = serializers.UUIDField(source="customer_id", required=False)
    can_edit = serializers.SerializerMethodField()

    class Meta:
        model = Vehicle
        fields = (
            "id", "customer", "customer_name", "vehicle_type", "brand", "model", "variant", "registration_number",
            "vin", "chassis_number", "engine_number", "fuel_type", "manufacturing_year", "color", "odometer",
            "insurance_expiry", "registration_expiry", "pollution_expiry", "notes", "is_active", "can_edit",
            "created_at", "updated_at",
        )
        read_only_fields = ("id", "customer_name", "is_active", "can_edit", "created_at", "updated_at")
        # Uniqueness is enforced (per customer) in VehicleService and by DB constraints.
        validators = []

    def get_can_edit(self, obj) -> bool:
        from .services import VehicleService

        request = self.context.get("request")
        return bool(request) and VehicleService.can_edit(obj, request.user)

    def validate_registration_number(self, value):
        normalized = normalize_registration(value)
        if not 4 <= len(normalized) <= 15:
            raise serializers.ValidationError("Enter a valid registration number.")
        return normalized

    def validate_vin(self, value):
        value = (value or "").strip().upper()
        if value and (len(value) != 17 or any(c in value for c in "IOQ") or not value.isalnum()):
            raise serializers.ValidationError("A VIN has 17 letters/digits and never contains I, O or Q.")
        return value

    def validate_manufacturing_year(self, value):
        if value and value > timezone.now().year + 1:
            raise serializers.ValidationError("Year cannot be in the future.")
        return value

    def validate(self, attrs):
        vtype = attrs.get("vehicle_type", getattr(self.instance, "vehicle_type", None))
        fuel = attrs.get("fuel_type", getattr(self.instance, "fuel_type", None))
        if vtype == VehicleType.EV and fuel and fuel != "ELECTRIC":
            raise serializers.ValidationError({"fuel_type": "EVs must use the ELECTRIC fuel type."})
        return attrs


class VehicleDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = VehicleDocument
        fields = ("id", "kind", "title", "file", "uploaded_by", "created_at")
        read_only_fields = ("id", "uploaded_by", "created_at")
