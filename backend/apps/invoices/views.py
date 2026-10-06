import django_filters
from django.http import FileResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from apps.accounts.constants import StaffPermission
from apps.bookings.models import Booking
from apps.core.permissions import HasStaffPermission, IsAgencyUser, IsCustomer, IsSuperAdmin

from .models import Invoice, InvoiceItem, InvoiceStatus
from .services import InvoiceService

CanView = HasStaffPermission(StaffPermission.INVOICE_VIEW)


class InvoiceItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceItem
        fields = ("id", "item_type", "description", "quantity", "unit_price", "discount", "tax_rate", "tax_amount",
                  "total")
        read_only_fields = fields


class InvoiceSerializer(serializers.ModelSerializer):
    items = InvoiceItemSerializer(many=True, read_only=True)
    customer_name = serializers.CharField(source="customer.full_name", read_only=True)
    organization_name = serializers.CharField(source="organization.name", read_only=True)
    booking_number = serializers.CharField(source="booking.booking_number", read_only=True, default=None)
    balance_due = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    has_pdf = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = ("id", "invoice_number", "status", "organization", "organization_name", "customer", "customer_name",
                  "booking", "booking_number", "subtotal", "discount", "tax", "total", "amount_paid", "balance_due",
                  "payment_status", "invoice_date", "due_date", "notes", "items", "has_pdf", "issued_at",
                  "voided_at", "void_reason", "created_at")
        read_only_fields = fields

    def get_has_pdf(self, obj) -> bool:
        return bool(obj.pdf)


class InvoiceListSerializer(InvoiceSerializer):
    class Meta(InvoiceSerializer.Meta):
        fields = tuple(f for f in InvoiceSerializer.Meta.fields if f != "items")
        read_only_fields = fields


class InvoiceUpdateSerializer(serializers.Serializer):
    discount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0, required=False)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class VoidSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500)


class GenerateSerializer(serializers.Serializer):
    booking = serializers.UUIDField()


class InvoiceFilter(django_filters.FilterSet):
    payment_status = django_filters.MultipleChoiceFilter(choices=[(s, s) for s in
                                                                  ("UNPAID", "PARTIALLY_PAID", "PAID", "REFUNDED")])
    date_from = django_filters.DateFilter(field_name="invoice_date", lookup_expr="gte")
    date_to = django_filters.DateFilter(field_name="invoice_date", lookup_expr="lte")

    class Meta:
        model = Invoice
        fields = ("status", "customer", "booking")


@extend_schema_view(
    list=extend_schema(tags=["invoices"], summary="Invoices (customer: own issued; agency: INVOICE_VIEW)"),
    retrieve=extend_schema(tags=["invoices"]),
)
class InvoiceViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    filterset_class = InvoiceFilter
    search_fields = ("invoice_number", "customer__full_name", "booking__booking_number")
    ordering_fields = ("invoice_date", "total", "created_at")
    ordering = ("-invoice_date", "-created_at")
    queryset = Invoice.objects.all()

    def get_permissions(self):
        if self.action in ("partial_update", "void", "generate"):
            return [(IsAgencyUser & CanView)()]
        return [(IsSuperAdmin | IsCustomer | (IsAgencyUser & CanView))()]

    def get_serializer_class(self):
        return InvoiceListSerializer if self.action == "list" else InvoiceSerializer

    def get_queryset(self):
        qs = Invoice.objects.for_user(self.request.user).select_related("customer", "organization", "booking")
        if self.request.query_params.get("organization") and self.request.user.is_super_admin:
            qs = qs.filter(organization_id=self.request.query_params["organization"])
        return qs if self.action == "list" else qs.prefetch_related("items")

    def _agency_admin_or_manager(self):
        from apps.core.exceptions import BusinessRuleViolation

        if self.request.user.role not in ("AGENCY_ADMIN", "AGENCY_MANAGER"):
            raise BusinessRuleViolation("Only agency admins and managers can change invoices.",
                                        code="PERMISSION_DENIED", status_code=403)

    @extend_schema(tags=["invoices"], summary="Change discount / notes (audited)", request=InvoiceUpdateSerializer,
                   responses={200: InvoiceSerializer})
    def partial_update(self, request, pk=None):
        self._agency_admin_or_manager()
        serializer = InvoiceUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        invoice = InvoiceService.update(invoice=self.get_object(), actor=request.user, request=request,
                                        **serializer.validated_data)
        return Response(InvoiceSerializer(Invoice.objects.prefetch_related("items").get(pk=invoice.pk)).data)

    @extend_schema(tags=["invoices"], summary="Void an unpaid invoice", request=VoidSerializer,
                   responses={200: InvoiceSerializer})
    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        self._agency_admin_or_manager()
        serializer = VoidSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invoice = InvoiceService.void(invoice=self.get_object(), actor=request.user, request=request,
                                      reason=serializer.validated_data["reason"])
        return Response(InvoiceSerializer(invoice).data)

    @extend_schema(tags=["invoices"], summary="Generate the invoice for a completed booking (idempotent)",
                   request=GenerateSerializer, responses={200: InvoiceSerializer})
    @action(detail=False, methods=["post"])
    def generate(self, request):
        serializer = GenerateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        booking = Booking.objects.for_user(request.user).filter(pk=serializer.validated_data["booking"],
                                                                status="COMPLETED").first()
        if booking is None:
            raise NotFound("Completed booking not found.")
        invoice = InvoiceService.generate_for_booking(booking, actor=request.user)
        return Response(InvoiceSerializer(Invoice.objects.prefetch_related("items").get(pk=invoice.pk)).data)

    @extend_schema(tags=["invoices"], summary="Download the PDF", responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"])
    def pdf(self, request, pk=None):
        invoice = self.get_object()
        if invoice.status == InvoiceStatus.VOID:
            raise NotFound("Void invoices have no PDF.")
        if not invoice.pdf:
            invoice = InvoiceService.render_pdf(invoice)
        return FileResponse(invoice.pdf.open("rb"), content_type="application/pdf", as_attachment=True,
                            filename=f"{invoice.invoice_number}.pdf")
