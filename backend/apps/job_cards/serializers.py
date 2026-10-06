from decimal import Decimal

from rest_framework import serializers

from .models import (
    AdditionalWorkRequest,
    InspectionArea,
    InspectionItem,
    InspectionResult,
    InspectionStage,
    JobCard,
    JobCardPart,
    JobCardPhoto,
)


class InspectionItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InspectionItem
        fields = ("id", "area", "stage", "result", "notes", "updated_at")
        read_only_fields = ("id", "updated_at")


class InspectionInputSerializer(serializers.Serializer):
    area = serializers.ChoiceField(choices=InspectionArea.choices)
    stage = serializers.ChoiceField(choices=InspectionStage.choices, default="BEFORE")
    result = serializers.ChoiceField(choices=InspectionResult.choices)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=1000, default="")


class InspectionBulkSerializer(serializers.Serializer):
    items = InspectionInputSerializer(many=True, allow_empty=False)


class JobCardPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobCardPhoto
        fields = ("id", "stage", "image", "caption", "created_at")
        read_only_fields = ("id", "created_at")


class AdditionalWorkSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdditionalWorkRequest
        fields = ("id", "description", "estimated_cost", "status", "customer_response", "approved_at",
                  "rejected_at", "auto_approved", "created_at")
        read_only_fields = ("id", "status", "customer_response", "approved_at", "rejected_at", "auto_approved",
                            "created_at")


class AdditionalWorkResponseSerializer(serializers.Serializer):
    approve = serializers.BooleanField()
    response = serializers.CharField(required=False, allow_blank=True, max_length=1000, default="")


class JobCardPartSerializer(serializers.ModelSerializer):
    part_name = serializers.CharField(source="part.name", read_only=True)
    sku = serializers.CharField(source="part.sku", read_only=True)
    net_quantity = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = JobCardPart
        fields = ("id", "part", "part_name", "sku", "quantity", "returned_quantity", "net_quantity", "unit_price",
                  "tax_rate", "created_at")
        read_only_fields = fields


class UsePartSerializer(serializers.Serializer):
    part = serializers.UUIDField()
    quantity = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))


class ReturnPartSerializer(serializers.Serializer):
    quantity = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))


class JobCardSerializer(serializers.ModelSerializer):
    booking = serializers.SerializerMethodField()
    vehicle = serializers.SerializerMethodField()
    customer = serializers.SerializerMethodField()
    inspection_items = InspectionItemSerializer(many=True, read_only=True)
    photos = JobCardPhotoSerializer(many=True, read_only=True)
    additional_work = AdditionalWorkSerializer(many=True, read_only=True)
    parts_used = JobCardPartSerializer(many=True, read_only=True)

    class Meta:
        model = JobCard
        fields = ("id", "job_card_number", "status", "booking", "vehicle", "customer", "inspection_notes",
                  "vehicle_condition", "odometer", "fuel_level", "existing_damage", "customer_requests",
                  "technician_notes", "inspection_items", "photos", "additional_work", "parts_used", "completed_at",
                  "closed_at", "created_at", "updated_at")
        read_only_fields = ("id", "job_card_number", "status", "booking", "vehicle", "customer", "inspection_items",
                            "photos", "additional_work", "parts_used", "completed_at", "closed_at", "created_at",
                            "updated_at")

    def get_booking(self, j) -> dict:
        b = j.booking
        return {"id": str(b.pk), "booking_number": b.booking_number, "status": b.status,
                "service": b.vendor_service.service.name, "start_datetime": b.start_datetime.isoformat(),
                "assigned_staff": b.assigned_staff.full_name if b.assigned_staff_id else None}

    def get_vehicle(self, j) -> dict:
        v = j.vehicle
        return {"id": str(v.pk), "brand": v.brand, "model": v.model, "registration_number": v.registration_number,
                "vehicle_type": v.vehicle_type}

    def get_customer(self, j) -> dict:
        return {"id": str(j.customer_id), "full_name": j.customer.full_name, "phone": j.customer.phone}

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if request and request.user.is_customer:
            for part in data.get("parts_used", []):
                part.pop("sku", None)
        return data


class JobCardListSerializer(JobCardSerializer):
    class Meta(JobCardSerializer.Meta):
        fields = ("id", "job_card_number", "status", "booking", "vehicle", "customer", "created_at", "updated_at")
        read_only_fields = fields
