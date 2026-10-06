from django.db.models import Count, Q
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.serializers import UserSerializer
from apps.accounts.services import AuthService
from apps.accounts.views import AuthRateThrottle
from apps.core.permissions import IsAgencyAdmin, IsAgencyManager, IsAgencyUser, IsSameOrganization, IsSuperAdmin

from .filters import OrganizationFilter
from .models import Membership, Organization
from .serializers import (
    AdminAgencyCreateSerializer,
    AgencyRegistrationResponseSerializer,
    AgencyRegistrationSerializer,
    MembershipSerializer,
    OrganizationSerializer,
    StatusChangeSerializer,
)
from .services import OrganizationService


class AgencyRegistrationView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AuthRateThrottle]

    @extend_schema(tags=["auth"], summary="Register a new agency (created as PENDING) with its first admin",
                   request=AgencyRegistrationSerializer, responses={201: AgencyRegistrationResponseSerializer})
    def post(self, request):
        serializer = AgencyRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        org_data, admin_data = serializer.split()
        org, admin = OrganizationService.register_agency(organization_data=org_data, admin_data=admin_data,
                                                         request=request)
        return Response(
            {
                "organization": OrganizationSerializer(org).data,
                "user": UserSerializer(admin).data,
                "tokens": AuthService.issue_tokens(admin),
            },
            status=status.HTTP_201_CREATED,
        )


_status_action_schema = extend_schema(tags=["organizations"], request=StatusChangeSerializer,
                                      responses={200: OrganizationSerializer})


@extend_schema_view(
    list=extend_schema(tags=["organizations"], summary="List agencies (Super Admin: all; agency users: own)"),
    retrieve=extend_schema(tags=["organizations"], summary="Retrieve an agency"),
    partial_update=extend_schema(tags=["organizations"], summary="Update agency profile (Agency Admin / Super Admin)"),
)
class OrganizationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin,
                          viewsets.GenericViewSet):
    """
    Tenant isolation: the queryset is built from ``Organization.objects.for_user``,
    so another agency's id resolves to 404 rather than leaking existence.
    """

    serializer_class = OrganizationSerializer
    queryset = Organization.objects.all()
    filterset_class = OrganizationFilter
    search_fields = ("name", "legal_name", "email", "phone", "city", "gst_number", "registration_number")
    ordering_fields = ("name", "created_at", "status", "city")
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    http_method_names = ["get", "patch", "post", "head", "options"]
    object_organization_attr = "pk"  # for IsSameOrganization: the object IS the organization

    def get_permissions(self):
        if self.action in ("create", "approve", "reject", "suspend", "reactivate", "deactivate"):
            classes = [IsSuperAdmin]
        elif self.action == "partial_update":
            classes = [IsSuperAdmin | (IsAgencyAdmin & IsSameOrganization)]
        elif self.action == "members":
            classes = [IsSuperAdmin | (IsAgencyManager & IsSameOrganization)]
        else:
            classes = [IsSuperAdmin | (IsAgencyUser & IsSameOrganization)]
        return [cls() for cls in classes]

    def get_queryset(self):
        # Aggregating queries ignore Meta.ordering, so order explicitly for stable pagination.
        return Organization.objects.for_user(self.request.user).annotate(
            member_count=Count("memberships", filter=Q(memberships__is_active=True))
        ).order_by("name", "id")

    @extend_schema(tags=["organizations"], summary="Create an ACTIVE agency with its first Agency Admin (Super Admin)",
                   request=AdminAgencyCreateSerializer, responses={201: OrganizationSerializer})
    def create(self, request):
        serializer = AdminAgencyCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        org_data, admin_data = serializer.split()
        org = OrganizationService.create_agency(organization_data=org_data, admin_data=admin_data,
                                                actor=request.user, request=request)
        return Response(OrganizationSerializer(self.get_queryset().get(pk=org.pk)).data,
                        status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        OrganizationService.update_profile(organization=serializer.instance, data=serializer.validated_data,
                                           actor=self.request.user, request=self.request)

    def _change_status(self, request, action_name):
        serializer = StatusChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        org = OrganizationService.change_status(organization=self.get_object(), action=action_name,
                                                actor=request.user, reason=serializer.validated_data["reason"],
                                                request=request)
        return Response(OrganizationSerializer(self.get_queryset().get(pk=org.pk)).data)

    @_status_action_schema
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self._change_status(request, "approve")

    @_status_action_schema
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self._change_status(request, "reject")

    @_status_action_schema
    @action(detail=True, methods=["post"])
    def suspend(self, request, pk=None):
        return self._change_status(request, "suspend")

    @_status_action_schema
    @action(detail=True, methods=["post"])
    def reactivate(self, request, pk=None):
        return self._change_status(request, "reactivate")

    @_status_action_schema
    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        return self._change_status(request, "deactivate")

    @extend_schema(tags=["organizations"], summary="List the agency's members",
                   responses={200: MembershipSerializer(many=True)})
    @action(detail=True, methods=["get"])
    def members(self, request, pk=None):
        org = self.get_object()
        qs = (
            Membership.objects.for_user(request.user)
            .filter(organization=org)
            .select_related("user")
            .order_by("user__full_name")
        )
        page = self.paginate_queryset(qs)
        serializer = MembershipSerializer(page if page is not None else qs, many=True)
        return self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)
