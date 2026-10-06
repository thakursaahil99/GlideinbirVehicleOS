from rest_framework import serializers

from apps.accounts.models import User
from apps.accounts.serializers import TokenPairSerializer, UserSerializer, validate_new_password

from .models import Membership, Organization

ORGANIZATION_PUBLIC_FIELDS = (
    "id", "name", "legal_name", "slug", "logo", "registration_number", "gst_number", "phone", "email",
    "website", "description", "address", "city", "state", "country", "pincode", "latitude", "longitude", "timezone",
    "status", "verification_status", "status_reason", "status_changed_at", "created_at", "updated_at",
)


class OrganizationSerializer(serializers.ModelSerializer):
    member_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = Organization
        fields = (*ORGANIZATION_PUBLIC_FIELDS, "member_count")
        # Status is changed only through the dedicated Super Admin actions.
        read_only_fields = ("id", "slug", "status", "verification_status", "status_reason",
                            "status_changed_at", "created_at", "updated_at", "member_count")


class StatusChangeSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=1000, default="")


class AgencyRegistrationSerializer(serializers.Serializer):
    # Agency
    name = serializers.CharField(max_length=200)
    legal_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    registration_number = serializers.CharField(max_length=64, required=False, allow_blank=True)
    gst_number = serializers.CharField(max_length=15, required=False, allow_blank=True)
    phone = serializers.RegexField(r"^\+?[0-9]{7,15}$", max_length=16)
    email = serializers.EmailField()
    address = serializers.CharField(required=False, allow_blank=True)
    city = serializers.CharField(max_length=100)
    state = serializers.CharField(max_length=100, required=False, allow_blank=True)
    country = serializers.CharField(max_length=100, required=False, default="India")
    pincode = serializers.CharField(max_length=10, required=False, allow_blank=True)
    # First Agency Admin
    admin_full_name = serializers.CharField(max_length=150)
    admin_email = serializers.EmailField(max_length=254)
    admin_phone = serializers.RegexField(r"^\+?[0-9]{7,15}$", max_length=16, required=False, allow_blank=True)
    admin_password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)

    def validate_gst_number(self, value):
        value = value.strip().upper()
        if value:
            Organization._meta.get_field("gst_number").run_validators(value)
        return value

    def validate_pincode(self, value):
        value = value.strip()
        if value:
            Organization._meta.get_field("pincode").run_validators(value)
        return value

    def validate_admin_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this e-mail already exists.")
        return value

    def validate(self, attrs):
        candidate = User(email=attrs["admin_email"], full_name=attrs["admin_full_name"])
        try:
            validate_new_password(attrs["admin_password"], candidate)
        except serializers.ValidationError as exc:
            raise serializers.ValidationError({"admin_password": exc.detail}) from exc
        return attrs

    def split(self):
        data = dict(self.validated_data)
        admin = {
            "full_name": data.pop("admin_full_name"),
            "email": data.pop("admin_email"),
            "phone": data.pop("admin_phone", ""),
            "password": data.pop("admin_password"),
        }
        return data, admin


class AgencyRegistrationResponseSerializer(serializers.Serializer):
    organization = OrganizationSerializer()
    user = UserSerializer()
    tokens = TokenPairSerializer()


class MemberUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "full_name", "phone", "role", "is_active", "last_login")
        read_only_fields = fields


class MembershipSerializer(serializers.ModelSerializer):
    user = MemberUserSerializer(read_only=True)

    class Meta:
        model = Membership
        fields = ("id", "user", "permissions", "is_active", "created_at")
        read_only_fields = fields
