from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.tenancy import get_user_membership

from .constants import AGENCY_ROLES, Role, StaffPermission
from .models import User


def validate_new_password(value, user=None):
    """Run Django's password validators, re-raised as a DRF field error."""
    try:
        password_validation.validate_password(value, user)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(list(exc.messages)) from exc
    return value


def _active_membership(user):
    """Use prefetched memberships when a list view provided them (avoids N+1)."""
    prefetched = getattr(user, "_prefetched_objects_cache", {}).get("memberships")
    if prefetched is not None:
        return next((m for m in prefetched if m.is_active), None)
    return get_user_membership(user)


class OrganizationSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    slug = serializers.SlugField()
    status = serializers.CharField()


class UserSerializer(serializers.ModelSerializer):
    organization = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id", "email", "full_name", "phone", "role", "profile_photo", "is_active", "email_verified",
            "date_joined", "last_login", "organization", "permissions",
        )
        read_only_fields = fields

    def get_organization(self, user) -> dict | None:
        membership = _active_membership(user)
        if membership is None:
            return None
        return OrganizationSummarySerializer(membership.organization).data

    def get_permissions(self, user) -> list[str]:
        if user.role in (Role.SUPER_ADMIN, Role.AGENCY_ADMIN):
            return list(StaffPermission.values)
        membership = _active_membership(user)
        return list(membership.permissions) if membership else []


class AdminUserSerializer(UserSerializer):
    """Used by Super Admin listings — no extra secrets, just the same shape."""


class AdminUserUpdateSerializer(serializers.Serializer):
    """Super Admin edits an account's details; a new password is optional."""

    email = serializers.EmailField(max_length=254, required=False)
    full_name = serializers.CharField(max_length=150, required=False)
    phone = serializers.RegexField(r"^\+?[0-9]{7,15}$", required=False, allow_blank=True, max_length=16)
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128, required=False,
                                     allow_blank=True)

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exclude(pk=self.instance.pk).exists():
            raise serializers.ValidationError("An account with this e-mail already exists.")
        return value

    def validate_password(self, value):
        if value:
            validate_new_password(value, self.instance)
        return value


class AdminUserCreateSerializer(serializers.Serializer):
    """Super Admin creates any account; agency roles need the agency they belong to."""

    email = serializers.EmailField(max_length=254)
    full_name = serializers.CharField(max_length=150)
    phone = serializers.RegexField(r"^\+?[0-9]{7,15}$", required=False, allow_blank=True, max_length=16, default="")
    role = serializers.ChoiceField(choices=Role.choices)
    organization = serializers.UUIDField(required=False, allow_null=True, default=None)
    permissions = serializers.ListField(child=serializers.ChoiceField(choices=StaffPermission.choices),
                                        required=False, allow_empty=True)
    # Blank = e-mail a link to set the password instead.
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128, required=False,
                                     allow_blank=True, default="")

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this e-mail already exists.")
        return value

    def validate(self, attrs):
        from apps.organizations.models import Organization

        if attrs["role"] in AGENCY_ROLES:
            if not attrs.get("organization"):
                raise serializers.ValidationError({"organization": ["Choose the agency this user belongs to."]})
            org = Organization.objects.filter(pk=attrs["organization"]).first()
            if org is None:
                raise serializers.ValidationError({"organization": ["Agency not found."]})
            attrs["organization"] = org
        else:
            attrs["organization"] = None
            attrs.pop("permissions", None)
        if attrs.get("password"):
            try:
                validate_new_password(attrs["password"], User(email=attrs["email"], full_name=attrs["full_name"]))
            except serializers.ValidationError as exc:
                raise serializers.ValidationError({"password": exc.detail}) from exc
        return attrs


class ProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("full_name", "phone", "profile_photo")
        extra_kwargs = {"full_name": {"required": False}}


class RegisterCustomerSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)
    full_name = serializers.CharField(max_length=150)
    phone = serializers.RegexField(r"^\+?[0-9]{7,15}$", required=False, allow_blank=True, max_length=16)

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this e-mail already exists.")
        return value

    def validate(self, attrs):
        candidate = User(email=attrs["email"], full_name=attrs["full_name"])
        try:
            validate_new_password(attrs["password"], candidate)
        except serializers.ValidationError as exc:
            raise serializers.ValidationError({"password": exc.detail}) from exc
        return attrs


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class TokenPairSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()


class AuthResponseSerializer(serializers.Serializer):
    user = UserSerializer()
    tokens = TokenPairSerializer()


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)

    def validate_new_password(self, value):
        return validate_new_password(value, self.context["request"].user)


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField(max_length=64)
    token = serializers.CharField(max_length=128)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128,
                                         validators=[validate_new_password])


class EmailVerifySerializer(serializers.Serializer):
    uid = serializers.CharField(max_length=64)
    token = serializers.CharField(max_length=128)


class SafeTokenRefreshSerializer(TokenRefreshSerializer):
    """Refresh rejects tokens of users deactivated after the token was issued."""

    def validate(self, attrs):
        refresh = RefreshToken(attrs["refresh"])
        user_id = refresh.payload.get(jwt_settings.USER_ID_CLAIM)
        if not User.objects.filter(pk=user_id, is_active=True).exists():
            raise AuthenticationFailed("User is inactive or no longer exists.", code="user_inactive")
        return super().validate(attrs)


class MessageSerializer(serializers.Serializer):
    message = serializers.CharField()
