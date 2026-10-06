from decimal import Decimal

import django_filters
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle, UserRateThrottle

from apps.accounts.constants import StaffPermission
from apps.core.permissions import HasStaffPermission, IsAgencyUser, IsCustomer, IsSuperAdmin

from .models import OFFLINE_METHODS, ONLINE_METHODS, Payment, PaymentMethod, PaymentRecordStatus
from .services import PaymentService

CanView = HasStaffPermission(StaffPermission.PAYMENT_VIEW)


class PaymentSerializer(serializers.ModelSerializer):
    invoice_number = serializers.CharField(source="invoice.invoice_number", read_only=True, default=None)
    booking_number = serializers.CharField(source="booking.booking_number", read_only=True, default=None)
    customer_name = serializers.CharField(source="customer.full_name", read_only=True)

    class Meta:
        model = Payment
        fields = ("id", "invoice", "invoice_number", "booking", "booking_number", "customer", "customer_name",
                  "amount", "refunded_amount", "currency", "method", "status", "gateway", "transaction_id",
                  "reference", "failure_reason", "paid_at", "created_at")
        read_only_fields = fields


class PayOnlineSerializer(serializers.Serializer):
    invoice = serializers.UUIDField(required=False)
    payment = serializers.UUIDField(required=False, help_text="A pending booking prepayment")
    method = serializers.ChoiceField(choices=sorted(ONLINE_METHODS))
    simulate = serializers.ChoiceField(choices=["success", "fail"], required=False,
                                       help_text="Mock gateway only: force the outcome")
    idempotency_key = serializers.CharField(required=False, max_length=64)

    def validate(self, attrs):
        if bool(attrs.get("invoice")) == bool(attrs.get("payment")):
            raise serializers.ValidationError("Provide exactly one of invoice or payment.")
        return attrs


class RecordOfflineSerializer(serializers.Serializer):
    invoice = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    method = serializers.ChoiceField(choices=sorted(OFFLINE_METHODS))
    reference = serializers.CharField(required=False, allow_blank=True, max_length=100, default="")


class RefundSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"), required=False)
    reason = serializers.CharField(max_length=300)


class PaymentFilter(django_filters.FilterSet):
    status = django_filters.MultipleChoiceFilter(choices=PaymentRecordStatus.choices)
    method = django_filters.MultipleChoiceFilter(choices=PaymentMethod.choices)
    date_from = django_filters.DateFilter(field_name="created_at", lookup_expr="date__gte")
    date_to = django_filters.DateFilter(field_name="created_at", lookup_expr="date__lte")

    class Meta:
        model = Payment
        fields = ("status", "method", "invoice", "booking")


class PaymentThrottle(ScopedRateThrottle):
    """Money-moving actions get their own, tighter budget."""

    def allow_request(self, request, view):
        if view.action not in ("pay", "record", "refund"):
            return True
        return super().allow_request(request, view)


@extend_schema_view(
    list=extend_schema(tags=["payments"], summary="Payments (customer: own; agency: PAYMENT_VIEW)"),
    retrieve=extend_schema(tags=["payments"]),
)
class PaymentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    throttle_scope = "payments"
    throttle_classes = [UserRateThrottle, PaymentThrottle]
    serializer_class = PaymentSerializer
    filterset_class = PaymentFilter
    search_fields = ("transaction_id", "reference", "invoice__invoice_number", "booking__booking_number")
    ordering = ("-created_at",)
    queryset = Payment.objects.all()

    def get_permissions(self):
        if self.action == "pay":
            return [IsCustomer()]
        if self.action in ("record", "refund"):
            return [(IsAgencyUser & CanView)()]
        return [(IsSuperAdmin | IsCustomer | (IsAgencyUser & CanView))()]

    def get_queryset(self):
        qs = Payment.objects.for_user(self.request.user).select_related("invoice", "booking", "customer")
        if self.request.query_params.get("organization") and self.request.user.is_super_admin:
            qs = qs.filter(organization_id=self.request.query_params["organization"])
        return qs

    @extend_schema(tags=["payments"], summary="Pay online through the gateway (mock in development)",
                   request=PayOnlineSerializer, responses={201: PaymentSerializer})
    @action(detail=False, methods=["post"])
    def pay(self, request):
        serializer = PayOnlineSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        payment = PaymentService.pay_online(actor=request.user, method=d["method"], invoice_id=d.get("invoice"),
                                            payment_id=d.get("payment"), simulate=d.get("simulate"),
                                            idempotency_key=d.get("idempotency_key"), request=request)
        code = status.HTTP_201_CREATED if payment.status == PaymentRecordStatus.SUCCEEDED else status.HTTP_200_OK
        return Response(PaymentSerializer(payment).data, status=code)

    @extend_schema(tags=["payments"], summary="Record a cash / bank transfer receipt",
                   request=RecordOfflineSerializer, responses={201: PaymentSerializer})
    @action(detail=False, methods=["post"])
    def record(self, request):
        serializer = RecordOfflineSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        payment = PaymentService.record_offline(actor=request.user, invoice_id=d["invoice"], amount=d["amount"],
                                                method=d["method"], reference=d["reference"], request=request)
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)

    @extend_schema(tags=["payments"], summary="Refund (agency admin)", request=RefundSerializer,
                   responses={200: PaymentSerializer})
    @action(detail=True, methods=["post"])
    def refund(self, request, pk=None):
        serializer = RefundSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = PaymentService.refund(actor=request.user, payment=self.get_object(), request=request,
                                        **serializer.validated_data)
        return Response(PaymentSerializer(payment).data)
