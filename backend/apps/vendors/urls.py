from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

agency_router = SimpleRouter()
agency_router.register("staff", views.StaffViewSet, basename="agency-staff")
agency_router.register("working-hours", views.WorkingHoursViewSet, basename="agency-working-hours")
agency_router.register("holidays", views.HolidayViewSet, basename="agency-holiday")
agency_router.register("special-days", views.SpecialWorkingDayViewSet, basename="agency-special-day")
agency_router.register("resources", views.ServiceResourceViewSet, basename="agency-resource")

agency_urlpatterns = [
    path("settings/", views.AgencySettingsView.as_view(), name="agency-settings"),
    *agency_router.urls,
]
