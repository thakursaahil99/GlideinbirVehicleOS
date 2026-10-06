from rest_framework import serializers

from apps.accounts.constants import Role, StaffPermission
from apps.accounts.models import User
from apps.accounts.serializers import validate_new_password
from apps.organizations.models import Membership, Organization

from .models import AgencySettings, Holiday, ResourceType, ServiceResource, SpecialWorkingDay, WorkingHours


# ---------------------------------------------------------------- staff
class StaffSerializer(serializers.ModelSerializer):
    user_id = serializers.UUIDField(source="user.id", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    phone = serializers.CharField(source="user.phone", read_only=True)
    role = serializers.CharField(source="user.role", read_only=True)
    profile_photo = serializers.ImageField(source="user.profile_photo", read_only=True)
    last_login = serializers.DateTimeField(source="user.last_login", read_only=True)
    user_is_active = serializers.BooleanField(source="user.is_active", read_only=True)

    class Meta:
        model = Membership
        fields = ("id", "user_id", "email", "full_name", "phone", "role", "profile_photo", "permissions",
                  "is_active", "user_is_active", "last_login", "created_at")
        read_only_fields = fields


class StaffCreateSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    full_name = serializers.CharField(max_length=150)
    phone = serializers.RegexField(r"^\+?[0-9]{7,15}$", max_length=16, required=False, allow_blank=True, default="")
    role = serializers.ChoiceField(choices=[Role.AGENCY_MANAGER, Role.AGENCY_STAFF, Role.AGENCY_ADMIN])
    permissions = serializers.ListField(child=serializers.ChoiceField(choices=StaffPermission.choices),
                                        required=False, allow_empty=True)
    # Optional: set the first password now; leave blank to e-mail an invite link instead.
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128, required=False,
                                     allow_blank=True, default="")

    def validate(self, attrs):
        if attrs.get("password"):
            candidate = User(email=attrs["email"], full_name=attrs["full_name"])
            try:
                validate_new_password(attrs["password"], candidate)
            except serializers.ValidationError as exc:
                raise serializers.ValidationError({"password": exc.detail}) from exc
        return attrs


class StaffUpdateSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=150, required=False)
    phone = serializers.RegexField(r"^\+?[0-9]{7,15}$", max_length=16, required=False, allow_blank=True)
    role = serializers.ChoiceField(choices=[Role.AGENCY_MANAGER, Role.AGENCY_STAFF, Role.AGENCY_ADMIN],
                                   required=False)
    permissions = serializers.ListField(child=serializers.ChoiceField(choices=StaffPermission.choices),
                                        required=False, allow_empty=True)


class PermissionCodeSerializer(serializers.Serializer):
    code = serializers.CharField()
    label = serializers.CharField()


# ---------------------------------------------------------------- schedule
class WorkingHoursSerializer(serializers.ModelSerializer):
    weekday_display = serializers.CharField(source="get_weekday_display", read_only=True)

    class Meta:
        model = WorkingHours
        fields = ("id", "weekday", "weekday_display", "opens_at", "closes_at")
        read_only_fields = ("id", "weekday_display")


class IntervalSerializer(serializers.Serializer):
    weekday = serializers.IntegerField(min_value=0, max_value=6)
    opens_at = serializers.TimeField()
    closes_at = serializers.TimeField()


class WeekScheduleSerializer(serializers.Serializer):
    intervals = IntervalSerializer(many=True, allow_empty=True)


class HolidaySerializer(serializers.ModelSerializer):
    class Meta:
        model = Holiday
        fields = ("id", "name", "start_date", "end_date", "kind", "notes", "created_at")
        read_only_fields = ("id", "created_at")

    def validate(self, attrs):
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": "End date must be on or after the start date."})
        return attrs


class SpecialWorkingDaySerializer(serializers.ModelSerializer):
    class Meta:
        model = SpecialWorkingDay
        fields = ("id", "date", "opens_at", "closes_at", "note")
        read_only_fields = fields


class DayIntervalSerializer(serializers.Serializer):
    opens_at = serializers.TimeField()
    closes_at = serializers.TimeField()
    note = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class SpecialDaySetSerializer(serializers.Serializer):
    date = serializers.DateField()
    intervals = DayIntervalSerializer(many=True, allow_empty=True)


# ---------------------------------------------------------------- resources & settings
class ServiceResourceSerializer(serializers.ModelSerializer):
    staff_name = serializers.CharField(source="staff.full_name", read_only=True, default=None)

    class Meta:
        model = ServiceResource
        fields = ("id", "name", "resource_type", "staff", "staff_name", "description", "active", "created_at")
        read_only_fields = ("id", "staff_name", "created_at")

    def validate(self, attrs):
        staff = attrs.get("staff", getattr(self.instance, "staff", None))
        rtype = attrs.get("resource_type", getattr(self.instance, "resource_type", None))
        if staff is not None:
            org = self.context["organization"]
            if not Membership.objects.filter(user=staff, organization=org, is_active=True).exists():
                raise serializers.ValidationError({"staff": "Staff member must belong to your agency."})
            if rtype != ResourceType.TECHNICIAN:
                raise serializers.ValidationError({"staff": "Only technician resources can be linked to staff."})
        name = attrs.get("name")
        if name:
            qs = ServiceResource.objects.filter(organization=self.context["organization"], name__iexact=name)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({"name": "A resource with this name already exists."})
        return attrs


class AgencySettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgencySettings
        fields = ("slot_interval_minutes", "buffer_minutes", "booking_lead_time_minutes", "max_advance_days",
                  "cancellation_cutoff_hours", "auto_confirm_bookings", "additional_work_requires_approval",
                  "require_online_payment", "updated_at")
        read_only_fields = ("updated_at",)


# ---------------------------------------------------------------- public vendor directory
class VendorPublicSerializer(serializers.ModelSerializer):
    """Only public-facing agency fields — no status reasons, registration data or member counts."""

    rating = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = ("id", "name", "slug", "logo", "description", "phone", "email", "website", "address", "city",
                  "state", "country", "pincode", "latitude", "longitude", "timezone", "rating")
        read_only_fields = fields

    def get_rating(self, obj) -> float | None:
        return None  # reviews & ratings are future scope


class VendorOfferSerializer(VendorPublicSerializer):
    """Directory row when filtering by service: includes that agency's price for comparison."""

    offer_id = serializers.UUIDField(read_only=True)
    offer_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    offer_duration = serializers.IntegerField(read_only=True)

    class Meta(VendorPublicSerializer.Meta):
        fields = (*VendorPublicSerializer.Meta.fields, "offer_id", "offer_price", "offer_duration")
        read_only_fields = fields


class PublicWorkingHoursSerializer(serializers.Serializer):
    weekday = serializers.IntegerField()
    weekday_display = serializers.CharField()
    opens_at = serializers.TimeField()
    closes_at = serializers.TimeField()


class PublicHolidaySerializer(serializers.Serializer):
    name = serializers.CharField()
    start_date = serializers.DateField()
    end_date = serializers.DateField()
