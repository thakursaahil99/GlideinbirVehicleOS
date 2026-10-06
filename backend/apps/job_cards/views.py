import django_filters
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.accounts.constants import StaffPermission
from apps.core.permissions import HasStaffPermission, IsAgencyUser, IsCustomer, IsSuperAdmin

from . import serializers as s
from .models import AdditionalWorkRequest, JobCard, JobCardPart, JobCardStatus
from .services import JobCardService, require_job_perm

CanView = HasStaffPermission(StaffPermission.JOB_CARD_VIEW)
PREFETCH = ("inspection_items", "photos", "additional_work", "parts_used__part")
SELECT = ("booking__vendor_service__service", "booking__assigned_staff", "vehicle", "customer")


class JobCardFilter(django_filters.FilterSet):
    status = django_filters.MultipleChoiceFilter(choices=JobCardStatus.choices)

    class Meta:
        model = JobCard
        fields = ("status", "vehicle", "customer")


@extend_schema_view(
    list=extend_schema(tags=["job-cards"], summary="Job cards (staff: assigned bookings; customer: own)"),
    retrieve=extend_schema(tags=["job-cards"], summary="Job card with inspection, photos, extra work and parts"),
)
class JobCardViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    filterset_class = JobCardFilter
    search_fields = ("job_card_number", "booking__booking_number", "vehicle__registration_number",
                     "customer__full_name")
    ordering = ("-created_at",)
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    queryset = JobCard.objects.all()

    def get_permissions(self):
        return [(IsSuperAdmin | IsCustomer | (IsAgencyUser & CanView))()]

    def get_serializer_class(self):
        return s.JobCardListSerializer if self.action == "list" else s.JobCardSerializer

    def get_queryset(self):
        qs = JobCard.objects.for_user(self.request.user).select_related(*SELECT)
        return qs if self.action == "list" else qs.prefetch_related(*PREFETCH)

    def _respond(self, job_card, code=status.HTTP_200_OK):
        fresh = JobCard.objects.select_related(*SELECT).prefetch_related(*PREFETCH).get(pk=job_card.pk)
        return Response(s.JobCardSerializer(fresh, context=self.get_serializer_context()).data, status=code)

    def _agency_only(self):
        if self.request.user.is_customer:
            raise NotFound()

    @extend_schema(tags=["job-cards"], summary="Update inspection details, odometer, fuel, notes",
                   request=s.JobCardSerializer, responses={200: s.JobCardSerializer})
    def partial_update(self, request, pk=None):
        self._agency_only()
        job_card = self.get_object()
        serializer = s.JobCardSerializer(job_card, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        JobCardService.update_details(job_card=job_card, actor=request.user, data=serializer.validated_data)
        return self._respond(job_card)

    @extend_schema(tags=["job-cards"], summary="Save inspection checklist results (upsert)",
                   request=s.InspectionBulkSerializer, responses={200: s.JobCardSerializer})
    @action(detail=True, methods=["put"])
    def inspection(self, request, pk=None):
        self._agency_only()
        job_card = self.get_object()
        serializer = s.InspectionBulkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        JobCardService.save_inspection(job_card=job_card, actor=request.user,
                                       items=serializer.validated_data["items"])
        return self._respond(job_card)

    @extend_schema(tags=["job-cards"], summary="Upload a before/after photo", request=s.JobCardPhotoSerializer,
                   responses={201: s.JobCardPhotoSerializer})
    @action(detail=True, methods=["post"])
    def photos(self, request, pk=None):
        self._agency_only()
        job_card = self.get_object()
        require_job_perm(request.user, job_card)
        serializer = s.JobCardPhotoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        photo = serializer.save(job_card=job_card, uploaded_by=request.user)
        return Response(s.JobCardPhotoSerializer(photo, context={"request": request}).data,
                        status=status.HTTP_201_CREATED)

    @extend_schema(tags=["job-cards"], summary="Start work", request=None, responses={200: s.JobCardSerializer})
    @action(detail=True, methods=["post"], url_path="start-work")
    def start_work(self, request, pk=None):
        self._agency_only()
        return self._respond(JobCardService.start_work(job_card=self.get_object(), actor=request.user))

    @extend_schema(tags=["job-cards"], summary="Request additional work (needs customer approval if configured)",
                   request=s.AdditionalWorkSerializer, responses={201: s.AdditionalWorkSerializer})
    @action(detail=True, methods=["post"], url_path="additional-work")
    def additional_work(self, request, pk=None):
        self._agency_only()
        serializer = s.AdditionalWorkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        req = JobCardService.request_additional_work(job_card=self.get_object(), actor=request.user,
                                                     request=request, **serializer.validated_data)
        return Response(s.AdditionalWorkSerializer(req).data, status=status.HTTP_201_CREATED)

    def _work_request(self, job_card, work_id):
        req = AdditionalWorkRequest.objects.filter(job_card=job_card, pk=work_id).first()
        if req is None:
            raise NotFound()
        return req

    @extend_schema(tags=["job-cards"], summary="Approve or decline additional work (customer, or agency on their behalf)",
                   request=s.AdditionalWorkResponseSerializer, responses={200: s.AdditionalWorkSerializer})
    @action(detail=True, methods=["post"], url_path=r"additional-work/(?P<work_id>[0-9a-f-]+)/respond")
    def respond_additional_work(self, request, pk=None, work_id=None):
        job_card = self.get_object()
        serializer = s.AdditionalWorkResponseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        req = JobCardService.respond_additional_work(work_request=self._work_request(job_card, work_id),
                                                     actor=request.user, request=request, **serializer.validated_data)
        return Response(s.AdditionalWorkSerializer(req).data)

    @extend_schema(tags=["job-cards"], summary="Withdraw a pending additional work request", request=None,
                   responses={200: s.AdditionalWorkSerializer})
    @action(detail=True, methods=["post"], url_path=r"additional-work/(?P<work_id>[0-9a-f-]+)/cancel")
    def cancel_additional_work(self, request, pk=None, work_id=None):
        self._agency_only()
        job_card = self.get_object()
        req = JobCardService.cancel_additional_work(work_request=self._work_request(job_card, work_id),
                                                    actor=request.user)
        return Response(s.AdditionalWorkSerializer(req).data)

    @extend_schema(tags=["job-cards"], summary="Use a part (reduces stock, writes a USED_IN_JOB transaction)",
                   request=s.UsePartSerializer, responses={201: s.JobCardPartSerializer})
    @action(detail=True, methods=["post"])
    def parts(self, request, pk=None):
        self._agency_only()
        serializer = s.UsePartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        usage = JobCardService.use_part(job_card=self.get_object(), actor=request.user,
                                        part_id=serializer.validated_data["part"],
                                        quantity=serializer.validated_data["quantity"])
        return Response(s.JobCardPartSerializer(usage).data, status=status.HTTP_201_CREATED)

    @extend_schema(tags=["job-cards"], summary="Return unused part quantity to stock",
                   request=s.ReturnPartSerializer, responses={200: s.JobCardPartSerializer})
    @action(detail=True, methods=["post"], url_path=r"parts/(?P<usage_id>[0-9a-f-]+)/return")
    def return_part(self, request, pk=None, usage_id=None):
        self._agency_only()
        job_card = self.get_object()
        usage = JobCardPart.objects.filter(job_card=job_card, pk=usage_id).first()
        if usage is None:
            raise NotFound()
        serializer = s.ReturnPartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        usage = JobCardService.return_part(usage=usage, actor=request.user,
                                           quantity=serializer.validated_data["quantity"])
        return Response(s.JobCardPartSerializer(usage).data)

    @extend_schema(tags=["job-cards"], summary="Complete the job (completes the booking and issues the invoice)",
                   request=None, responses={200: s.JobCardSerializer})
    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        self._agency_only()
        job_card = JobCardService.complete(job_card=self.get_object(), actor=request.user,
                                           technician_notes=request.data.get("technician_notes"), request=request)
        return self._respond(job_card)

    @extend_schema(tags=["job-cards"], summary="Close a completed job card", request=None,
                   responses={200: s.JobCardSerializer})
    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        self._agency_only()
        return self._respond(JobCardService.close(job_card=self.get_object(), actor=request.user))
