from django.contrib import admin
from .models import Assignment, AssignmentSubmission


class AssignmentSubmissionInline(admin.TabularInline):
    model = AssignmentSubmission
    extra = 0
    fields = ("student", "file", "submitted_at", "is_late", "status", "marks", "graded_by")
    readonly_fields = ("submitted_at", "is_late")
    show_change_link = True


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "course",
        "created_by",
        "due_date",
        "maximum_marks",
        "is_past_due",
        "allow_resubmission",
        "created_at",
    )
    list_filter = ("course", "created_by", "allow_resubmission", "due_date", "created_at")
    search_fields = (
        "title",
        "description",
        "course__title",
        "course__code",
        "created_by__username",
        "created_by__first_name",
        "created_by__last_name",
    )
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("created_at", "updated_at")
    inlines = [AssignmentSubmissionInline]
    ordering = ("-due_date", "-created_at")


@admin.register(AssignmentSubmission)
class AssignmentSubmissionAdmin(admin.ModelAdmin):
    list_display = (
        "assignment",
        "student",
        "submitted_at",
        "is_late",
        "status",
        "marks",
        "graded_by",
        "graded_at",
    )
    list_filter = (
        "status",
        "is_late",
        "assignment__course",
        "graded_at",
        "submitted_at",
    )
    search_fields = (
        "assignment__title",
        "assignment__course__code",
        "student__student__username",
        "student__student__first_name",
        "student__student__last_name",
        "feedback",
        "comment",
    )
    readonly_fields = ("submitted_at", "graded_at")
    ordering = ("-submitted_at",)
