from django.contrib import admin

from .models import AgencySettings, Holiday, ServiceResource, SpecialWorkingDay, WorkingHours


@admin.register(AgencySettings)
class AgencySettingsAdmin(admin.ModelAdmin):
    list_display = ("organization", "auto_confirm_bookings", "buffer_minutes", "max_advance_days")
    list_select_related = ("organization",)


@admin.register(WorkingHours)
class WorkingHoursAdmin(admin.ModelAdmin):
    list_display = ("organization", "weekday", "opens_at", "closes_at")
    list_filter = ("weekday",)
    list_select_related = ("organization",)


@admin.register(Holiday)
class HolidayAdmin(admin.ModelAdmin):
    list_display = ("organization", "name", "start_date", "end_date", "kind")
    list_filter = ("kind",)
    list_select_related = ("organization",)


@admin.register(SpecialWorkingDay)
class SpecialWorkingDayAdmin(admin.ModelAdmin):
    list_display = ("organization", "date", "opens_at", "closes_at")
    list_select_related = ("organization",)


@admin.register(ServiceResource)
class ServiceResourceAdmin(admin.ModelAdmin):
    list_display = ("organization", "name", "resource_type", "staff", "active")
    list_filter = ("resource_type", "active")
    list_select_related = ("organization", "staff")
