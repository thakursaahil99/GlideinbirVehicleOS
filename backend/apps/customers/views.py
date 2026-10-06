import django_filters
from django.db.models import Count, Q
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.accounts.constants import StaffPermission
from apps.core.permissions import HasStaffPermission, IsAgencyUser, IsCustomer, IsSuperAdmin
from apps.core.tenancy import get_user_organization

from .models import Customer, CustomerNote
from .serializers import (
    CustomerCreateSerializer,
    CustomerDetailSerializer,
    CustomerNoteSerializer,
    CustomerSerializer,
)
from .services import CustomerService

CanView = HasStaffPermission(StaffPermission.CUSTOMER_VIEW)
CanCreate = HasStaffPermission(StaffPermission.CUSTOMER_CREATE)
CanUpdate = HasStaffPermission(StaffPermission.CUSTOMER_UPDATE)


class CustomerFilter(django_filters.FilterSet):
    city = django_filters.CharFilter(lookup_expr="iexact")
    source = django_filters.CharFilter(field_name="agency_links__source")
    walk_in = django_filters.BooleanFilter(field_name="user", lookup_expr="isnull")

    class Meta:
        model = Customer
        fields = ("city",)


@extend_schema_view(
    list=extend_schema(tags=["customers"], summary="Customers (agency: linked to your agency; Super Admin: all)"),
    retrieve=extend_schema(tags=["customers"], summary="Customer profile with vehicles"),
)
class CustomerViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Customer.objects.all()
    filterset_class = CustomerFilter
    search_fields = ("full_name", "phone", "email", "vehicles__registration_number", "vehicles__vin")
    ordering_fields = ("full_name", "created_at", "city")
    ordering = ("full_name",)

    def get_permissions(self):
        if self.action in ("me", "my_timeline"):
            return [IsCustomer()]
        if self.action == "create":
            return [(IsAgencyUser & CanCreate)()]
        if self.action == "notes":  # internal notes are agency-only
            return [(IsAgencyUser & (CanUpdate if self.request.method == "POST" else CanView))()]
        if self.action == "partial_update":
            return [(IsSuperAdmin | (IsAgencyUser & CanUpdate))()]
        return [(IsSuperAdmin | (IsAgencyUser & CanView))()]

    def get_serializer_class(self):
        return CustomerDetailSerializer if self.action in ("retrieve", "partial_update", "me") else CustomerSerializer

    def get_queryset(self):
        qs = Customer.objects.for_user(self.request.user)
        if self.action == "list":
            qs = qs.annotate(vehicle_count=Count("vehicles", filter=Q(vehicles__is_active=True), distinct=True))
            if self.request.query_params.get("search"):
                qs = qs.distinct()
        return qs

    @extend_schema(tags=["customers"], summary="Register a walk-in customer for your agency",
                   request=CustomerCreateSerializer, responses={201: CustomerDetailSerializer})
    def create(self, request):
        serializer = CustomerCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        customer = CustomerService.create_walk_in(organization=get_user_organization(request.user),
                                                  actor=request.user, data=serializer.validated_data,
                                                  request=request)
        return Response(CustomerDetailSerializer(customer, context=self.get_serializer_context()).data,
                        status=status.HTTP_201_CREATED)

    @extend_schema(tags=["customers"], summary="Update a customer (agency: own walk-ins only)",
                   request=CustomerCreateSerializer, responses={200: CustomerDetailSerializer})
    def partial_update(self, request, pk=None):
        customer = self.get_object()
        serializer = CustomerCreateSerializer(customer, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        org = None if request.user.is_super_admin else get_user_organization(request.user)
        CustomerService.update_profile(customer=customer, data=serializer.validated_data, actor=request.user,
                                       organization=org, request=request)
        return Response(CustomerDetailSerializer(customer, context=self.get_serializer_context()).data)

    @extend_schema(tags=["customers"], summary="Internal notes (tenant-private)",
                   request=CustomerNoteSerializer, responses={200: CustomerNoteSerializer(many=True)})
    @action(detail=True, methods=["get", "post"])
    def notes(self, request, pk=None):
        customer = self.get_object()
        org = get_user_organization(request.user)
        if request.method == "POST":
            serializer = CustomerNoteSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            note = CustomerService.add_note(customer=customer, organization=org, author=request.user,
                                            body=serializer.validated_data["body"])
            return Response(CustomerNoteSerializer(note).data, status=status.HTTP_201_CREATED)
        notes = CustomerNote.objects.for_user(request.user).filter(customer=customer).select_related("author")
        page = self.paginate_queryset(notes)
        return self.get_paginated_response(CustomerNoteSerializer(page, many=True).data)

    @extend_schema(tags=["customers"], summary="My customer profile", request=CustomerCreateSerializer,
                   responses={200: CustomerDetailSerializer})
    @action(detail=False, methods=["get", "patch"])
    def me(self, request):
        customer = CustomerService.ensure_profile(request.user)
        if request.method == "PATCH":
            serializer = CustomerCreateSerializer(customer, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            if "email" in serializer.validated_data:
                raise PermissionDenied("Your e-mail is tied to your login and cannot be changed here.")
            CustomerService.update_profile(customer=customer, data=serializer.validated_data, actor=request.user,
                                           request=request)
        return Response(CustomerDetailSerializer(customer, context=self.get_serializer_context()).data)

    def _summary(self, customer, organization_id):
        from django.db.models import Sum
        from django.utils import timezone

        from apps.bookings.models import ACTIVE_STATUSES
        from apps.bookings.serializers import BookingSerializer
        from apps.invoices.models import Invoice
        from apps.payments.models import Payment

        bookings = customer.bookings.all()
        invoices = Invoice.objects.filter(customer=customer, status="ISSUED")
        payments = Payment.objects.settled().filter(customer=customer)
        if organization_id:
            bookings = bookings.filter(organization_id=organization_id)
            invoices = invoices.filter(organization_id=organization_id)
            payments = payments.filter(organization_id=organization_id)
        now = timezone.now()
        upcoming = bookings.filter(status__in=ACTIVE_STATUSES, start_datetime__gte=now).select_related(
            "organization", "customer", "vehicle", "vendor_service__service", "assigned_staff", "assigned_resource")
        history = bookings.filter(start_datetime__lt=now).select_related(
            "organization", "customer", "vehicle", "vendor_service__service", "assigned_staff",
            "assigned_resource").order_by("-start_datetime")[:20]
        spent = sum((p.net_amount for p in payments), 0)
        pending = invoices.exclude(payment_status="PAID").aggregate(t=Sum("total"), p=Sum("amount_paid"))
        ctx = self.get_serializer_context()
        return {
            "total_spending": f"{spent:.2f}",
            "pending_payments": f"{(pending['t'] or 0) - (pending['p'] or 0):.2f}",
            "bookings_count": bookings.count(),
            "completed_services": bookings.filter(status="COMPLETED").count(),
            "upcoming_bookings": BookingSerializer(upcoming.order_by("start_datetime")[:10], many=True,
                                                   context=ctx).data,
            "booking_history": BookingSerializer(history, many=True, context=ctx).data,
        }

    @extend_schema(tags=["customers"], summary="Profile summary: upcoming, history, spending, pending payments")
    @action(detail=True, methods=["get"])
    def summary(self, request, pk=None):
        from apps.core.tenancy import get_user_organization_id

        customer = self.get_object()
        org_id = None if request.user.is_super_admin else get_user_organization_id(request.user)
        return Response(self._summary(customer, org_id))

    @extend_schema(tags=["customers"], summary="Customer timeline (agency: own-agency events only)")
    @action(detail=True, methods=["get"])
    def timeline(self, request, pk=None):
        from apps.core.tenancy import get_user_organization_id
        from apps.reports.timeline import customer_timeline

        customer = self.get_object()
        org_id = None if request.user.is_super_admin else get_user_organization_id(request.user)
        return Response(customer_timeline(customer, organization_id=org_id))

    @extend_schema(tags=["customers"], summary="My timeline across all agencies")
    @action(detail=False, methods=["get"], url_path="me/timeline")
    def my_timeline(self, request):
        from apps.reports.timeline import customer_timeline

        return Response(customer_timeline(CustomerService.ensure_profile(request.user)))
