from django.contrib import admin
from .models import AcademicEvent


@admin.register(AcademicEvent)
class AcademicEventAdmin(admin.ModelAdmin):
    list_display = ("title", "event_type", "start_date", "end_date", "location", "is_published")
    list_filter = ("event_type", "is_published", "start_date")
    search_fields = ("title", "description", "location")
    readonly_fields = ("created_at", "updated_at")
