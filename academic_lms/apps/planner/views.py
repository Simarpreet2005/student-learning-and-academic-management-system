"""Views for Rule-Based Smart Academic Workload Planner.

Enforces strict server-side authorization boundaries across all four user roles.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.models import ParentStudentRelationship, Role, User
from apps.academics.models import Course, CourseAllocation
from .forms import StudentStudyBudgetForm
from .models import StudentStudyBudget
from .permissions import (
    can_manage_student_workload_preferences,
    can_view_course_workload,
    can_view_student_workload,
)
from .services import WorkloadPlannerService


@login_required
def student_workload_dashboard_view(request: HttpRequest) -> HttpResponse:
    """Personalized workload dashboard for students (or administrative inspection)."""
    user = request.user

    # 1. Admin inspecting a specific student
    if getattr(user, "is_admin_role", False) or user.is_superuser:
        target_student_id = request.GET.get("student_id")
        if target_student_id:
            student = get_object_or_404(User, id=target_student_id, role=Role.STUDENT)
        else:
            # Provide directory of enrolled students for admin selection
            students = User.objects.filter(role=Role.STUDENT, is_active=True).order_by(
                "first_name", "last_name"
            )
            return render(
                request,
                "planner/admin_student_picker.html",
                {"students": students},
            )
    elif getattr(user, "is_student_role", False):
        student = user
    elif getattr(user, "is_parent_role", False):
        # Redirect parent to their first linked child's workload view
        relationship = ParentStudentRelationship.objects.filter(parent=user).first()
        if relationship:
            return redirect("planner:student_workload", student_id=relationship.student.id)
        messages.info(request, "No students are currently linked to your parent observer account.")
        return redirect("accounts:parent_dashboard")
    elif getattr(user, "is_lecturer_role", False):
        # Redirect lecturer to their first allocated course
        alloc = CourseAllocation.objects.filter(lecturer=user, is_active=True).first()
        if alloc:
            return redirect("planner:course_workload", course_id=alloc.course.id)
        messages.info(request, "You have no active course allocations to inspect.")
        return redirect("accounts:lecturer_dashboard")
    else:
        raise PermissionDenied("You do not have access to the Workload Planner.")

    # Calculate deterministic workload summary
    summary = WorkloadPlannerService.get_student_workload(student)

    context = {
        "summary": summary,
        "is_admin_view": (user != student),
        "target_student": student,
    }
    return render(request, "planner/dashboard.html", context)


@login_required
def study_budget_preferences_view(request: HttpRequest) -> HttpResponse:
    """View and update weekly available study hours by weekday."""
    user = request.user
    if not (getattr(user, "is_student_role", False) or getattr(user, "is_admin_role", False) or user.is_superuser):
        raise PermissionDenied("Only students can configure their personal study budget.")

    student = user
    if (getattr(user, "is_admin_role", False) or user.is_superuser) and request.GET.get("student_id"):
        student = get_object_or_404(User, id=request.GET.get("student_id"), role=Role.STUDENT)

    budget, created = StudentStudyBudget.objects.get_or_create(student=student)

    if request.method == "POST":
        form = StudentStudyBudgetForm(request.POST, instance=budget)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                "Your weekly study hours preferences have been saved successfully. "
                "The planner has updated your workload capacity and schedule."
            )
            return redirect("planner:dashboard")
    else:
        form = StudentStudyBudgetForm(instance=budget)

    context = {
        "form": form,
        "budget": budget,
        "student": student,
    }
    return render(request, "planner/preferences.html", context)


@login_required
def course_workload_view(request: HttpRequest, course_id: int) -> HttpResponse:
    """Course-level deliverable clusters and submission statistics for allocated lecturers."""
    course = get_object_or_404(Course, id=course_id, is_active=True)

    if not can_view_course_workload(request.user, course):
        raise PermissionDenied("You are not authorized to view workload analytics for this course.")

    course_data = WorkloadPlannerService.get_course_workload(course)

    context = {
        "course": course,
        "course_data": course_data,
    }
    return render(request, "planner/course_workload.html", context)


@login_required
def parent_student_workload_view(request: HttpRequest, student_id: int) -> HttpResponse:
    """Read-only observer view of a linked student's workload summary for parents."""
    student = get_object_or_404(User, id=student_id, role=Role.STUDENT)

    if not can_view_student_workload(request.user, student):
        raise PermissionDenied("You do not have authorized observer permission to view this student's workload plan.")

    summary = WorkloadPlannerService.get_student_workload(student)

    # Fetch parent's other linked students for quick navigation
    other_children = []
    if getattr(request.user, "is_parent_role", False):
        other_children = ParentStudentRelationship.objects.filter(
            parent=request.user
        ).select_related("student")

    context = {
        "summary": summary,
        "student": student,
        "other_children": other_children,
    }
    return render(request, "planner/parent_summary.html", context)