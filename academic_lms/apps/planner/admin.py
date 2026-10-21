from django.contrib import admin
from .models import StudentStudyBudget, TaskEffortProfile


@admin.register(StudentStudyBudget)
class StudentStudyBudgetAdmin(admin.ModelAdmin):
    list_display = (
        "student",
        "monday_hours",
        "tuesday_hours",
        "wednesday_hours",
        "thursday_hours",
        "friday_hours",
        "saturday_hours",
        "sunday_hours",
        "target_weekly_hours",
        "updated_at",
    )
    search_fields = (
        "student__email",
        "student__username",
        "student__first_name",
        "student__last_name",
    )
    readonly_fields = ("created_at", "updated_at")


@admin.register(TaskEffortProfile)
class TaskEffortProfileAdmin(admin.ModelAdmin):
    list_display = ("task_type", "default_effort_hours", "updated_at")
    list_editable = ("default_effort_hours",)
    search_fields = ("task_type", "description")
