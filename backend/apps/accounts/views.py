import django_filters
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenRefreshView

from apps.core.permissions import IsSuperAdmin

from . import serializers as s
from .constants import Role
from .models import User
from .services import AuthService, UserService


class AuthRateThrottle(AnonRateThrottle):
    """Tight limit for credential endpoints, keyed by client IP."""

    scope = "auth"


class RegisterView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    @extend_schema(tags=["auth"], summary="Register a customer account", request=s.RegisterCustomerSerializer,
                   responses={201: s.AuthResponseSerializer})
    def post(self, request):
        serializer = s.RegisterCustomerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = AuthService.register_customer(**serializer.validated_data, request=request)
        tokens = AuthService.issue_tokens(user)
        return Response({"user": s.UserSerializer(user).data, "tokens": tokens}, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AuthRateThrottle]

    @extend_schema(tags=["auth"], summary="Log in with e-mail and password", request=s.LoginSerializer,
                   responses={200: s.AuthResponseSerializer})
    def post(self, request):
        serializer = s.LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user, tokens = AuthService.login(**serializer.validated_data, request=request)
        return Response({"user": s.UserSerializer(user).data, "tokens": tokens})


@extend_schema(tags=["auth"], summary="Rotate the refresh token and get a new access token")
class RefreshView(TokenRefreshView):
    serializer_class = s.SafeTokenRefreshSerializer
    throttle_classes = [AuthRateThrottle]


class LogoutView(APIView):
    @extend_schema(tags=["auth"], summary="Log out (blacklists the refresh token)", request=s.LogoutSerializer,
                   responses={200: s.MessageSerializer})
    def post(self, request):
        serializer = s.LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        AuthService.logout(user=request.user, refresh_token=serializer.validated_data["refresh"], request=request)
        return Response({"message": "Logged out."})


class MeView(generics.GenericAPIView):
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    serializer_class = s.UserSerializer

    @extend_schema(tags=["auth"], summary="Current user profile, role, organization and permissions")
    def get(self, request):
        return Response(s.UserSerializer(request.user).data)

    @extend_schema(tags=["auth"], summary="Update own profile", request=s.ProfileUpdateSerializer,
                   responses={200: s.UserSerializer})
    def patch(self, request):
        serializer = s.ProfileUpdateSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        user = UserService.update_profile(user=request.user, data=serializer.validated_data, request=request)
        return Response(s.UserSerializer(user).data)


class ChangePasswordView(APIView):
    @extend_schema(tags=["auth"], summary="Change password (revokes all refresh tokens)",
                   request=s.ChangePasswordSerializer, responses={200: s.MessageSerializer})
    def post(self, request):
        serializer = s.ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        AuthService.change_password(user=request.user, request=request, **serializer.validated_data)
        return Response({"message": "Password changed. Please log in again on other devices."})


class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AuthRateThrottle]

    @extend_schema(tags=["auth"], summary="Request a password-reset e-mail",
                   request=s.PasswordResetRequestSerializer, responses={200: s.MessageSerializer})
    def post(self, request):
        serializer = s.PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        AuthService.request_password_reset(email=serializer.validated_data["email"], request=request)
        return Response({"message": "If an account exists for this e-mail, a reset link has been sent."})


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AuthRateThrottle]

    @extend_schema(tags=["auth"], summary="Set a new password using the e-mailed token",
                   request=s.PasswordResetConfirmSerializer, responses={200: s.MessageSerializer})
    def post(self, request):
        serializer = s.PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        AuthService.confirm_password_reset(**serializer.validated_data, request=request)
        return Response({"message": "Password has been reset. You can now log in."})


class VerifyEmailView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AuthRateThrottle]

    @extend_schema(tags=["auth"], summary="Confirm e-mail address", request=s.EmailVerifySerializer,
                   responses={200: s.MessageSerializer})
    def post(self, request):
        serializer = s.EmailVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        AuthService.verify_email(**serializer.validated_data, request=request)
        return Response({"message": "E-mail verified."})


class ResendVerificationView(APIView):
    throttle_classes = [AuthRateThrottle]

    @extend_schema(tags=["auth"], summary="Re-send the verification e-mail", request=None,
                   responses={200: s.MessageSerializer})
    def post(self, request):
        AuthService.send_verification(request.user)
        return Response({"message": "Verification e-mail sent."})


class UserFilter(django_filters.FilterSet):
    role = django_filters.MultipleChoiceFilter(choices=Role.choices)

    class Meta:
        model = User
        fields = ("role", "is_active", "email_verified")


@extend_schema_view(
    list=extend_schema(tags=["users"], summary="List all users (Super Admin)"),
    retrieve=extend_schema(tags=["users"], summary="Retrieve a user (Super Admin)"),
)
class UserViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Platform-wide user management. Agency staff management arrives in Phase 2 (vendors app)."""

    serializer_class = s.AdminUserSerializer
    permission_classes = [IsSuperAdmin]
    filterset_class = UserFilter
    search_fields = ("email", "full_name", "phone")
    ordering_fields = ("date_joined", "email", "full_name", "last_login")
    queryset = User.objects.all()

    def get_queryset(self):
        return User.objects.prefetch_related("memberships__organization")

    @extend_schema(tags=["users"], summary="Create a user of any role (Super Admin)",
                   request=s.AdminUserCreateSerializer, responses={201: s.AdminUserSerializer})
    def create(self, request):
        serializer = s.AdminUserCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = UserService.create_user(actor=request.user, request=request, **serializer.validated_data)
        return Response(self.get_serializer(self.get_queryset().get(pk=user.pk)).data,
                        status=status.HTTP_201_CREATED)

    @extend_schema(tags=["users"], summary="Activate a user", request=None, responses={200: s.AdminUserSerializer})
    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        user = UserService.set_active(target=self.get_object(), active=True, actor=request.user, request=request)
        return Response(self.get_serializer(user).data)

    @extend_schema(tags=["users"], summary="Deactivate a user (revokes their refresh tokens)", request=None,
                   responses={200: s.AdminUserSerializer})
    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        user = UserService.set_active(target=self.get_object(), active=False, actor=request.user, request=request)
        return Response(self.get_serializer(user).data)
