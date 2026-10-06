from django.utils import timezone
from rest_framework import serializers

from .models import Vehicle, VehicleDocument, VehicleModel, VehicleSale, VehicleType, normalize_registration


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


class VehicleModelSerializer(serializers.ModelSerializer):
    is_low_stock = serializers.BooleanField(read_only=True)
    vehicle_type_display = serializers.CharField(source="get_vehicle_type_display", read_only=True)

    class Meta:
        model = VehicleModel
        fields = ("id", "vehicle_type", "vehicle_type_display", "brand", "name", "variant", "launch_year",
                  "fuel_type", "engine_cc", "colours", "ex_showroom_price", "stock_quantity", "minimum_stock",
                  "is_low_stock", "is_active", "notes", "created_at", "updated_at")
        read_only_fields = ("id", "is_low_stock", "vehicle_type_display", "created_at", "updated_at")
        # Uniqueness per agency is enforced by the DB constraint; organization is stamped server-side.
        validators = []

    def validate_launch_year(self, value):
        if value is not None and not 1950 <= value <= 2100:
            raise serializers.ValidationError("Enter a valid year.")
        return value


class StockAdjustSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(help_text="Positive = units received, negative = units sold/out")
    note = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")

    def validate_quantity(self, value):
        if value == 0:
            raise serializers.ValidationError("Quantity cannot be zero.")
        return value


class VehicleSaleSerializer(serializers.ModelSerializer):
    vehicle_model_name = serializers.SerializerMethodField()
    sold_by_name = serializers.CharField(source="sold_by.full_name", read_only=True, default=None)
    buyer_phone = serializers.RegexField(r"^\+?[0-9]{7,15}$", max_length=16)

    class Meta:
        model = VehicleSale
        fields = ("id", "vehicle_model", "vehicle_model_name", "customer", "buyer_name", "buyer_phone", "buyer_email",
                  "buyer_address", "colour", "chassis_number", "engine_number", "registration_number", "sale_price",
                  "payment_mode", "invoice_number", "sold_on", "sold_by", "sold_by_name", "notes",
                  "created_at", "updated_at")
        read_only_fields = ("id", "vehicle_model_name", "sold_by", "sold_by_name", "created_at", "updated_at")

    def get_vehicle_model_name(self, obj) -> str:
        return str(obj.vehicle_model)

    def validate(self, attrs):
        # Foreign keys must belong to the caller's agency (tenant isolation).
        org_id = self.context.get("organization_id")
        vm = attrs.get("vehicle_model")
        if vm is not None and vm.organization_id != org_id:
            raise serializers.ValidationError({"vehicle_model": ["Vehicle model not found."]})
        customer = attrs.get("customer")
        if customer is not None:
            from apps.customers.models import Customer

            if not Customer.objects.for_user(self.context["request"].user).filter(pk=customer.pk).exists():
                raise serializers.ValidationError({"customer": ["Customer not found."]})
        return attrs
