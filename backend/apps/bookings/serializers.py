from rest_framework import serializers

from .models import Booking, BookingReschedule, BookingStatusHistory
from .services import allowed_actions

STATUS_COLORS = {
    "PENDING": "#f59e0b", "CONFIRMED": "#0ea5e9", "ASSIGNED": "#6366f1", "VEHICLE_RECEIVED": "#8b5cf6",
    "IN_PROGRESS": "#5243e6", "WAITING_FOR_APPROVAL": "#d97706", "COMPLETED": "#10b981", "CANCELLED": "#f43f5e",
    "REJECTED": "#e11d48", "NO_SHOW": "#64748b",
}


class BookingSerializer(serializers.ModelSerializer):
    organization = serializers.SerializerMethodField()
    customer = serializers.SerializerMethodField()
    vehicle = serializers.SerializerMethodField()
    service = serializers.SerializerMethodField()
    assigned_staff = serializers.SerializerMethodField()
    assigned_resource = serializers.SerializerMethodField()
    allowed_actions = serializers.SerializerMethodField()
    status_color = serializers.SerializerMethodField()
    job_card_id = serializers.SerializerMethodField()
    invoice_id = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = (
            "id", "booking_number", "status", "status_color", "payment_status", "source", "organization", "customer",
            "vehicle", "service", "vendor_service", "booking_date", "start_datetime", "end_datetime",
            "duration_minutes", "quoted_price", "tax_rate", "assigned_staff", "assigned_resource", "customer_notes",
            "internal_notes", "pickup_requested", "drop_requested", "pickup_address", "confirmed_at", "completed_at",
            "cancelled_at", "cancellation_reason", "allowed_actions", "job_card_id", "invoice_id", "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if request and request.user.is_customer:
            data.pop("internal_notes", None)  # never shown to customers
        return data

    def get_organization(self, b) -> dict:
        return {"id": str(b.organization_id), "name": b.organization.name, "phone": b.organization.phone}

    def get_customer(self, b) -> dict:
        return {"id": str(b.customer_id), "full_name": b.customer.full_name, "phone": b.customer.phone}

    def get_vehicle(self, b) -> dict:
        v = b.vehicle
        return {"id": str(v.pk), "brand": v.brand, "model": v.model, "registration_number": v.registration_number,
                "vehicle_type": v.vehicle_type}

    def get_service(self, b) -> dict:
        s = b.vendor_service.service
        return {"id": str(s.pk), "name": s.name, "category": s.category}

    def get_assigned_staff(self, b) -> dict | None:
        return {"id": str(b.assigned_staff_id), "full_name": b.assigned_staff.full_name} if b.assigned_staff_id else None

    def get_assigned_resource(self, b) -> dict | None:
        r = b.assigned_resource
        return {"id": str(r.pk), "name": r.name, "resource_type": r.resource_type} if r else None

    def get_allowed_actions(self, b) -> list[str]:
        request = self.context.get("request")
        return allowed_actions(b, request.user) if request else []

    def get_status_color(self, b) -> str:
        return STATUS_COLORS.get(b.status, "#64748b")

    def get_job_card_id(self, b) -> str | None:
        job = getattr(b, "job_card", None)
        return str(job.pk) if job else None

    def get_invoice_id(self, b) -> str | None:
        invoice = getattr(b, "invoice", None)
        return str(invoice.pk) if invoice else None


class BookingCreateSerializer(serializers.Serializer):
    vendor_service = serializers.UUIDField()
    vehicle = serializers.UUIDField()
    start_datetime = serializers.DateTimeField(help_text="ISO 8601 with timezone, exactly as returned by /availability/slots/")
    customer = serializers.UUIDField(required=False, help_text="Agency users: the customer being booked")
    customer_notes = serializers.CharField(required=False, allow_blank=True, max_length=2000, default="")
    pickup_requested = serializers.BooleanField(required=False, default=False)
    drop_requested = serializers.BooleanField(required=False, default=False)
    pickup_address = serializers.CharField(required=False, allow_blank=True, max_length=500, default="")


class BookingNotesSerializer(serializers.Serializer):
    customer_notes = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    internal_notes = serializers.CharField(required=False, allow_blank=True, max_length=4000)


class NoteSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, max_length=1000, default="")


class CancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=1000)


class RescheduleSerializer(serializers.Serializer):
    start_datetime = serializers.DateTimeField()
    reason = serializers.CharField(required=False, allow_blank=True, max_length=1000, default="")


class AssignSerializer(serializers.Serializer):
    staff = serializers.UUIDField(required=False, allow_null=True)
    resource = serializers.UUIDField(required=False, allow_null=True)

    def validate(self, attrs):
        if not attrs.get("staff") and not attrs.get("resource"):
            raise serializers.ValidationError("Provide staff and/or resource.")
        return attrs


class StatusHistorySerializer(serializers.ModelSerializer):
    changed_by_name = serializers.CharField(source="changed_by.full_name", default=None, read_only=True)

    class Meta:
        model = BookingStatusHistory
        fields = ("id", "from_status", "to_status", "changed_by_name", "note", "created_at")
        read_only_fields = fields


class RescheduleHistorySerializer(serializers.ModelSerializer):
    rescheduled_by_name = serializers.CharField(source="rescheduled_by.full_name", default=None, read_only=True)

    class Meta:
        model = BookingReschedule
        fields = ("id", "old_start", "old_end", "new_start", "new_end", "reason", "rescheduled_by_name", "created_at")
        read_only_fields = fields


class CalendarEventSerializer(serializers.ModelSerializer):
    title = serializers.SerializerMethodField()
    start = serializers.DateTimeField(source="start_datetime")
    end = serializers.DateTimeField(source="end_datetime")
    color = serializers.SerializerMethodField()
    extended = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = ("id", "title", "start", "end", "color", "status", "extended")
        read_only_fields = fields

    def get_title(self, b) -> str:
        return f"{b.vendor_service.service.name} · {b.vehicle.registration_number}"

    def get_color(self, b) -> str:
        return STATUS_COLORS.get(b.status, "#64748b")

    def get_extended(self, b) -> dict:
        return {
            "booking_number": b.booking_number, "customer": b.customer.full_name,
            "vehicle": f"{b.vehicle.brand} {b.vehicle.model} ({b.vehicle.registration_number})",
            "service": b.vendor_service.service.name, "organization": b.organization.name,
            "staff": b.assigned_staff.full_name if b.assigned_staff_id else None,
            "resource": b.assigned_resource.name if b.assigned_resource_id else None,
        }
