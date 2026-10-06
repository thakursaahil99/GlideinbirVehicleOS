import django_filters
from django.db.models import Q
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.accounts.constants import StaffPermission
from apps.core.permissions import HasStaffPermission, IsAgencyUser, IsCustomer, IsSuperAdmin

from .models import Vehicle, VehicleDocument
from .serializers import VehicleDocumentSerializer, VehicleSerializer
from .services import VehicleService

CanView = HasStaffPermission(StaffPermission.VEHICLE_VIEW)
CanCreate = HasStaffPermission(StaffPermission.VEHICLE_CREATE)


class VehicleFilter(django_filters.FilterSet):
    customer = django_filters.UUIDFilter(field_name="customer_id")
    expiring_before = django_filters.DateFilter(method="filter_expiring")

    class Meta:
        model = Vehicle
        fields = ("vehicle_type", "fuel_type", "is_active")

    def filter_expiring(self, qs, name, value):
        return qs.filter(Q(insurance_expiry__lte=value) | Q(pollution_expiry__lte=value)
                         | Q(registration_expiry__lte=value))


@extend_schema_view(
    list=extend_schema(tags=["vehicles"], summary="Vehicles (customer: own; agency: linked customers' vehicles)"),
    retrieve=extend_schema(tags=["vehicles"]),
    create=extend_schema(tags=["vehicles"], summary="Add a vehicle (agency users must pass `customer`)"),
    partial_update=extend_schema(tags=["vehicles"]),
    destroy=extend_schema(tags=["vehicles"], summary="Archive a vehicle (kept in service history)"),
)
class VehicleViewSet(viewsets.ModelViewSet):
    serializer_class = VehicleSerializer
    filterset_class = VehicleFilter
    search_fields = ("registration_number", "vin", "brand", "model", "customer__full_name", "customer__phone")
    ordering_fields = ("brand", "model", "created_at", "manufacturing_year")
    ordering = ("brand", "model")
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    queryset = Vehicle.objects.all()

    def get_permissions(self):
        agency_perm = CanView if self.action in ("list", "retrieve") or (
            self.action == "documents" and self.request.method == "GET") else CanCreate
        return [(IsSuperAdmin | IsCustomer | (IsAgencyUser & agency_perm))()]

    def get_queryset(self):
        qs = Vehicle.objects.for_user(self.request.user).select_related("customer")
        if self.action == "list" and self.request.query_params.get("is_active") is None:
            qs = qs.filter(is_active=True)
        return qs

    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        customer = VehicleService.resolve_owner(actor=request.user, customer_id=data.pop("customer_id", None))
        vehicle = VehicleService.create(actor=request.user, customer=customer, data=data, request=request)
        return Response(self.get_serializer(vehicle).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        vehicle = self.get_object()
        serializer = self.get_serializer(vehicle, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        data.pop("customer_id", None)  # ownership never changes through the API
        vehicle = VehicleService.update(vehicle=vehicle, actor=request.user, data=data, request=request)
        return Response(self.get_serializer(vehicle).data)

    def destroy(self, request, pk=None):
        VehicleService.archive(vehicle=self.get_object(), actor=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(tags=["vehicles"], summary="List or upload vehicle documents (RC, insurance, PUC, photos)",
                   request=VehicleDocumentSerializer, responses={200: VehicleDocumentSerializer(many=True)})
    @action(detail=True, methods=["get", "post"])
    def documents(self, request, pk=None):
        vehicle = self.get_object()
        if request.method == "POST":
            if not VehicleService.can_edit(vehicle, request.user):
                raise PermissionDenied("Only the owner can add documents to this vehicle.")
            serializer = VehicleDocumentSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            doc = serializer.save(vehicle=vehicle, uploaded_by=request.user)
            return Response(VehicleDocumentSerializer(doc, context={"request": request}).data,
                            status=status.HTTP_201_CREATED)
        docs = VehicleDocument.objects.filter(vehicle=vehicle)
        return Response(VehicleDocumentSerializer(docs, many=True, context={"request": request}).data)

    @extend_schema(tags=["vehicles"], summary="Delete a vehicle document", request=None, responses={204: None})
    @action(detail=True, methods=["delete"], url_path=r"documents/(?P<doc_id>[0-9a-f-]+)")
    def delete_document(self, request, pk=None, doc_id=None):
        vehicle = self.get_object()
        if not VehicleService.can_edit(vehicle, request.user):
            raise PermissionDenied("Only the owner can delete documents of this vehicle.")
        doc = VehicleDocument.objects.filter(vehicle=vehicle, pk=doc_id).first()
        if doc is None:
            raise NotFound()
        doc.file.delete(save=False)
        doc.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
