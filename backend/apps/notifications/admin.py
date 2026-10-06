from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("event", "channel", "recipient", "to_address", "status", "created_at")
    list_filter = ("channel", "status", "event")
    search_fields = ("to_address", "title")
