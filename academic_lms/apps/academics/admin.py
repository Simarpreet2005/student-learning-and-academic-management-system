"""Django Admin configuration for Academics models."""
from django.contrib import admin
from .models import (
    Department,
    AcademicProgram,
    AcademicYear,
    Semester,
    Course,
    CourseAllocation,
    StudentEnrollment,
)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["code", "name"]


@admin.register(AcademicProgram)
class AcademicProgramAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "department", "is_active"]
    list_filter = ["is_active", "department"]
    search_fields = ["code", "name"]


@admin.register(AcademicYear)
class AcademicYearAdmin(admin.ModelAdmin):
    list_display = ["name", "start_date", "end_date", "is_current"]
    list_filter = ["is_current"]
    search_fields = ["name"]


@admin.register(Semester)
class SemesterAdmin(admin.ModelAdmin):
    list_display = ["name", "academic_year", "semester_type", "start_date", "end_date", "is_active"]
    list_filter = ["is_active", "semester_type", "academic_year"]
    search_fields = ["name", "academic_year__name"]


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ["code", "title", "credits", "department", "is_active"]
    list_filter = ["is_active", "department"]
    search_fields = ["code", "title", "description"]


@admin.register(CourseAllocation)
class CourseAllocationAdmin(admin.ModelAdmin):
    list_display = ["course", "lecturer", "semester", "is_active", "created_at"]
    list_filter = ["is_active", "semester"]
    search_fields = ["course__code", "course__title", "lecturer__username", "lecturer__email"]


@admin.register(StudentEnrollment)
class StudentEnrollmentAdmin(admin.ModelAdmin):
    list_display = ["student", "course", "semester", "status", "is_active", "created_at"]
    list_filter = ["status", "is_active", "semester"]
    search_fields = ["student__username", "student__email", "course__code", "course__title"]
