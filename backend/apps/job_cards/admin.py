from django.contrib import admin

from .models import AdditionalWorkRequest, InspectionItem, JobCard, JobCardPart, JobCardPhoto


@admin.register(JobCard)
class JobCardAdmin(admin.ModelAdmin):
    list_display = ("job_card_number", "organization", "vehicle", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("job_card_number", "vehicle__registration_number")
    raw_id_fields = ("booking", "vehicle", "customer")


for model in (InspectionItem, JobCardPhoto, AdditionalWorkRequest, JobCardPart):
    admin.site.register(model)
