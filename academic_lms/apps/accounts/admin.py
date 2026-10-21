"""Django admin configuration for accounts app."""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import (
    User,
    StudentProfile,
    LecturerProfile,
    ParentProfile,
    ParentStudentRelationship,
)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin configuration for custom User model."""

    list_display = (
        "email",
        "username",
        "role",
        "is_staff",
        "is_active",
        "date_joined",
    )
    list_filter = ("role", "is_staff", "is_superuser", "is_active")
    search_fields = ("email", "username", "first_name", "last_name")
    ordering = ("-date_joined",)

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            "Personal Information",
            {"fields": ("username", "first_name", "last_name")},
        ),
        (
            "Role & Permissions",
            {
                "fields": (
                    "role",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important Dates", {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "username",
                    "role",
                    "password1",
                    "password2",
                    "is_staff",
                    "is_active",
                ),
            },
        ),
    )


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ("student_id", "user", "program", "current_semester", "phone")
    search_fields = ("student_id", "user__email", "user__username", "program")
    list_filter = ("current_semester",)


@admin.register(LecturerProfile)
class LecturerProfileAdmin(admin.ModelAdmin):
    list_display = ("employee_id", "user", "department", "office_location", "phone")
    search_fields = ("employee_id", "user__email", "user__username", "department")
    list_filter = ("department",)


@admin.register(ParentProfile)
class ParentProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "phone", "address")
    search_fields = ("user__email", "user__username", "phone")


@admin.register(ParentStudentRelationship)
class ParentStudentRelationshipAdmin(admin.ModelAdmin):
    list_display = ("parent", "student", "relationship_type", "created_at")
    list_filter = ("relationship_type",)
    search_fields = (
        "parent__email",
        "parent__username",
        "student__email",
        "student__username",
    )
