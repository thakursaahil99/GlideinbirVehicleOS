from rest_framework import serializers

from apps.vehicles.models import Vehicle

from .models import Customer, CustomerNote


class CustomerVehicleSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehicle
        fields = ("id", "vehicle_type", "brand", "model", "registration_number", "is_active")
        read_only_fields = fields


class CustomerSerializer(serializers.ModelSerializer):
    is_walk_in = serializers.BooleanField(read_only=True)
    has_account = serializers.SerializerMethodField()
    vehicle_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = Customer
        fields = ("id", "full_name", "phone", "email", "address", "city", "state", "country", "pincode", "notes",
                  "is_walk_in", "has_account", "vehicle_count", "created_at", "updated_at")
        read_only_fields = ("id", "is_walk_in", "has_account", "vehicle_count", "created_at", "updated_at")

    def get_has_account(self, obj) -> bool:
        return obj.user_id is not None


class CustomerDetailSerializer(CustomerSerializer):
    vehicles = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()

    class Meta(CustomerSerializer.Meta):
        fields = (*CustomerSerializer.Meta.fields, "vehicles", "can_edit")

    def get_vehicles(self, obj) -> list[dict]:
        return CustomerVehicleSummarySerializer(obj.vehicles.filter(is_active=True), many=True).data

    def get_can_edit(self, obj) -> bool:
        from .services import CustomerService

        return CustomerService.can_edit_identity(obj, self.context["request"].user)


class CustomerCreateSerializer(serializers.ModelSerializer):
    phone = serializers.RegexField(r"^\+?[0-9]{7,15}$", max_length=16)

    class Meta:
        model = Customer
        fields = ("full_name", "phone", "email", "address", "city", "state", "country", "pincode", "notes")


class CustomerNoteSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.full_name", read_only=True, default=None)

    class Meta:
        model = CustomerNote
        fields = ("id", "body", "author", "author_name", "created_at")
        read_only_fields = ("id", "author", "author_name", "created_at")
