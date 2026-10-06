"""Root URLconf — Vehicle Service CRM, built by Sahil Thakur."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import SimpleRouter

from apps.accounts.views import UserViewSet
from apps.audit_logs.views import AuditLogViewSet
from apps.availability.views import DaysView, SlotsView
from apps.bookings.views import BookingViewSet
from apps.inventory.views import PartViewSet
from apps.invoices.views import InvoiceViewSet
from apps.job_cards.views import JobCardViewSet
from apps.notifications.views import NotificationViewSet
from apps.payments.views import PaymentViewSet
from apps.reports.views import DashboardView, ReportListView, ReportView, SearchView
from apps.core.views import HealthView
from apps.customers.views import CustomerViewSet
from apps.organizations.views import OrganizationViewSet
from apps.vendors.urls import agency_urlpatterns
from apps.services.views import ServiceViewSet, VendorServiceViewSet
from apps.vehicles.views import VehicleViewSet
from apps.vendors.views import VendorDirectoryViewSet

router = SimpleRouter()
router.register("users", UserViewSet, basename="user")
router.register("organizations", OrganizationViewSet, basename="organization")
router.register("audit-logs", AuditLogViewSet, basename="audit-log")
router.register("vendors", VendorDirectoryViewSet, basename="vendor")
router.register("customers", CustomerViewSet, basename="customer")
router.register("vehicles", VehicleViewSet, basename="vehicle")
router.register("services", ServiceViewSet, basename="service")
router.register("vendor-services", VendorServiceViewSet, basename="vendor-service")
router.register("bookings", BookingViewSet, basename="booking")
router.register("job-cards", JobCardViewSet, basename="job-card")
router.register("inventory/parts", PartViewSet, basename="part")
router.register("payments", PaymentViewSet, basename="payment")
router.register("invoices", InvoiceViewSet, basename="invoice")
router.register("notifications", NotificationViewSet, basename="notification")

api_v1 = [
    path("health/", HealthView.as_view(), name="health"),
    path("auth/", include("apps.accounts.urls")),
    path("agency/", include(agency_urlpatterns)),
    path("availability/slots/", SlotsView.as_view(), name="availability-slots"),
    path("availability/days/", DaysView.as_view(), name="availability-days"),
    path("reports/", ReportListView.as_view(), name="report-list"),
    path("reports/dashboard/", DashboardView.as_view(), name="dashboard"),
    path("reports/<slug:name>/", ReportView.as_view(), name="report-detail"),
    path("search/", SearchView.as_view(), name="global-search"),
    *router.urls,
]

if settings.API_DOCS_ENABLED:
    api_v1 += [
        path("schema/", SpectacularAPIView.as_view(), name="schema"),
        path("docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    ]

urlpatterns = [
    path(settings.DJANGO_ADMIN_URL, admin.site.urls),
    path("api/v1/", include(api_v1)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler404 = "apps.core.views.json_404"
handler500 = "apps.core.views.json_500"
