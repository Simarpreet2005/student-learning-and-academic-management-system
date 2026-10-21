"""Django Admin configuration for Courseware models."""
from django.contrib import admin
from .models import CourseModule, LearningResource


@admin.register(CourseModule)
class CourseModuleAdmin(admin.ModelAdmin):
    list_display = ["title", "course", "order", "is_active", "created_at"]
    list_filter = ["is_active", "course"]
    search_fields = ["title", "description", "course__code", "course__title"]


@admin.register(LearningResource)
class LearningResourceAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "course",
        "module",
        "resource_type",
        "status",
        "created_by",
        "is_active",
        "created_at",
    ]
    list_filter = ["status", "resource_type", "is_active", "course"]
    search_fields = [
        "title",
        "description",
        "course__code",
        "course__title",
        "created_by__email",
        "created_by__username",
    ]
    date_hierarchy = "created_at"
