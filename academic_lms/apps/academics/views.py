"""Student self-service course enrollment views."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .models import (
    Course,
    CourseAllocation,
    EnrollmentStatus,
    Semester,
    StudentEnrollment,
)


@login_required
def enrollment_catalog_view(request):
    """List course offerings for an active semester and allow students to add/drop."""
    if not request.user.is_student_role:
        raise PermissionDenied("Only students can manage their own course enrollment.")

    today = timezone.localdate()
    semesters = Semester.objects.filter(
        is_active=True,
        academic_year__is_current=True,
        start_date__lte=today,
        end_date__gte=today,
    ).select_related("academic_year")
    semester_id = request.GET.get("semester") or request.POST.get("semester")
    if semester_id:
        semester = get_object_or_404(semesters, pk=semester_id)
    else:
        semester = semesters.order_by("start_date").first()

    if request.method == "POST":
        if semester is None:
            messages.error(request, "There is no active enrollment period right now.")
            return redirect("academics:enrollment_catalog")
        course = get_object_or_404(
            Course.objects.filter(
                is_active=True,
                allocations__is_active=True,
                allocations__semester=semester,
            ).distinct(),
            pk=request.POST.get("course_id"),
        )
        action = request.POST.get("action")
        if action == "drop":
            enrollment = StudentEnrollment.objects.filter(
                student=request.user, course=course, semester=semester,
                status=EnrollmentStatus.ENROLLED, is_active=True,
            ).first()
            if enrollment:
                enrollment.status = EnrollmentStatus.DROPPED
                enrollment.is_active = False
                enrollment.save(update_fields=["status", "is_active", "updated_at"])
                messages.success(request, f"You dropped {course.code}.")
            else:
                messages.info(request, f"You are not enrolled in {course.code}.")
        elif action == "enroll":
            enrollment, created = StudentEnrollment.objects.get_or_create(
                student=request.user,
                course=course,
                semester=semester,
                defaults={"status": EnrollmentStatus.ENROLLED, "is_active": True},
            )
            if created or enrollment.status != EnrollmentStatus.ENROLLED or not enrollment.is_active:
                enrollment.status = EnrollmentStatus.ENROLLED
                enrollment.is_active = True
                enrollment.save(update_fields=["status", "is_active", "updated_at"])
                messages.success(request, f"You enrolled in {course.code}.")
            else:
                messages.info(request, f"You are already enrolled in {course.code}.")
        return redirect(f"{reverse('academics:enrollment_catalog')}?semester={semester.pk}")

    courses = Course.objects.none()
    enrollments = StudentEnrollment.objects.none()
    if semester:
        offered_ids = CourseAllocation.objects.filter(
            semester=semester, is_active=True
        ).values_list("course_id", flat=True)
        courses = Course.objects.filter(is_active=True, pk__in=offered_ids).select_related("department").distinct()
        enrollments = StudentEnrollment.objects.filter(
            student=request.user, semester=semester
        ).select_related("course")
    enrollment_by_course = {item.course_id: item for item in enrollments}
    course_rows = [(course, enrollment_by_course.get(course.pk)) for course in courses]
    return render(request, "academics/enrollment_catalog.html", {
        "semesters": semesters,
        "selected_semester": semester,
        "course_rows": course_rows,
    })
