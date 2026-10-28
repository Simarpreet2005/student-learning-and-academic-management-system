from django.contrib import admin
from .models import Assignment, AssignmentSubmission


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "course",
        "created_by",
        "due_date",
        "maximum_marks",
        "estimated_effort_hours",
        "is_published",
        "is_active",
    )
    list_filter = ("course", "is_published", "is_active", "due_date")
    search_fields = ("title", "description", "course__title", "course__code")
    readonly_fields = ("created_at", "updated_at")


@admin.register(AssignmentSubmission)
class AssignmentSubmissionAdmin(admin.ModelAdmin):
    list_display = (
        "assignment",
        "student",
        "status",
        "submitted_at",
        "submission_file",
        "score",
        "is_active",
    )
    list_filter = ("status", "is_active", "submitted_at")
    search_fields = (
        "assignment__title",
        "student__email",
        "student__username",
        "student__first_name",
        "student__last_name",
    )
    readonly_fields = ("submitted_at", "created_at", "updated_at")
