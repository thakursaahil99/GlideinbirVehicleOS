from datetime import date
from decimal import Decimal

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from apps.accounts.constants import StaffPermission
from apps.core.tenancy import get_user_membership

from .exporters import to_csv, to_xlsx
from .search import global_search
from .services import REPORTS, DashboardService, Scope, build_report

FILTER_PARAMS = [
    OpenApiParameter("date_from", OpenApiTypes.DATE), OpenApiParameter("date_to", OpenApiTypes.DATE),
    OpenApiParameter("organization", OpenApiTypes.UUID, description="Super Admin only"),
    OpenApiParameter("vehicle_type", str), OpenApiParameter("service", OpenApiTypes.UUID),
    OpenApiParameter("status", str),
]


def money_safe(value):
    """Decimals leave the API as fixed 2-dp strings, never floats."""
    if isinstance(value, Decimal):
        return f"{value.quantize(Decimal('0.01'))}"
    if isinstance(value, dict):
        return {k: money_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [money_safe(v) for v in value]
    return value


def _date(value, name):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError({name: ["Use YYYY-MM-DD."]}) from exc


def resolve_scope(request, require_report_perm=True):
    """Super Admin: platform (or ?organization=). Agency: own org with REPORT_VIEW. Others: denied."""
    user, params = request.user, request.query_params
    if user.is_super_admin:
        org_id = params.get("organization") or None
    else:
        membership = get_user_membership(user)
        if membership is None:
            raise PermissionDenied("Reports are available to agencies and Super Admins.")
        if require_report_perm and not membership.has_permission(StaffPermission.REPORT_VIEW):
            raise PermissionDenied("You do not have permission to view reports.")
        org_id = membership.organization_id  # never from the query string
    scope = Scope(organization_id=org_id, date_from=_date(params.get("date_from"), "date_from"),
                  date_to=_date(params.get("date_to"), "date_to"), vehicle_type=params.get("vehicle_type") or None,
                  service_id=params.get("service") or None, status=params.get("status") or None)
    if (scope.date_to - scope.date_from).days > 731:
        raise ValidationError({"date_from": ["The range is limited to two years."]})
    return scope


class DashboardView(APIView):
    @extend_schema(tags=["reports"], summary="Role-specific dashboard (stats + chart series)",
                   parameters=FILTER_PARAMS, responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        user = request.user
        if user.is_customer:
            return Response(money_safe({"role": "CUSTOMER", **DashboardService.customer(user)}))
        # Dashboards are visible to every agency member; detailed reports need REPORT_VIEW.
        scope = resolve_scope(request, require_report_perm=False)
        if user.is_super_admin:
            return Response(money_safe({"role": "SUPER_ADMIN", **DashboardService.super_admin(scope)}))
        return Response(money_safe({"role": "AGENCY", **DashboardService.agency(scope)}))


class ReportListView(APIView):
    @extend_schema(tags=["reports"], summary="Reports available to you", operation_id="reports_list",
                   responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        audience = "admin" if request.user.is_super_admin else "agency"
        resolve_scope(request)
        return Response([{"name": name, "title": title} for name, (aud, title, _b) in REPORTS.items()
                         if aud in (audience, "both")])


class ReportView(APIView):
    @extend_schema(tags=["reports"], summary="Run a report; ?export=csv|xlsx downloads it", operation_id="reports_run",
                   parameters=[*FILTER_PARAMS, OpenApiParameter("export", str, enum=["csv", "xlsx"])],
                   responses={200: OpenApiTypes.OBJECT})
    def get(self, request, name):
        if name not in REPORTS:
            raise NotFound("Unknown report.")
        audience = REPORTS[name][0]
        scope = resolve_scope(request)
        if audience == "admin" and not request.user.is_super_admin:
            raise PermissionDenied("This report is for Super Admins.")
        if audience == "agency" and request.user.is_super_admin and not scope.organization_id:
            raise ValidationError({"organization": ["Pick an agency for this report."]})
        report = build_report(name, scope)
        fmt = request.query_params.get("export", "json")
        if fmt == "csv":
            return to_csv(report)
        if fmt == "xlsx":
            return to_xlsx(report)
        return Response(money_safe(report))


class SearchView(APIView):
    throttle_scope = "search"
    throttle_classes = [UserRateThrottle, ScopedRateThrottle]

    @extend_schema(tags=["search"], summary="Global search (customers, vehicles, bookings, invoices, job cards, vendors)",
                   parameters=[OpenApiParameter("q", str, required=True)], responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        q = (request.query_params.get("q") or "").strip()
        if len(q) < 2:
            raise ValidationError({"q": ["Type at least 2 characters."]})
        return Response(global_search(request.user, q[:100]))
