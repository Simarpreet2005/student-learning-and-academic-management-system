"""Views for apps.core: Landing showcase and Institutional Academic Calendar."""
import calendar
from datetime import date, datetime, timedelta
from typing import List, Optional

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone

from apps.accounts.models import ParentStudentRelationship, Role, User
from apps.academics.models import Course, CourseAllocation, StudentEnrollment
from .models import AcademicEvent
from .services import CalendarService


def index_view(request: HttpRequest) -> HttpResponse:
    """Render the Academic LMS landing page."""
    context = {
        "title": "Empowering Higher Education",
        "system_name": "Academic LMS",
        "roles": [
            {
                "name": "Administrator",
                "tag": "ADMIN",
                "icon": "fa-shield-halved",
                "color": "var(--color-primary-espresso)",
                "description": "Comprehensive academic oversight. Manage departments, curricula, user accounts, course allocations, and institutional term structures.",
            },
            {
                "name": "Lecturer",
                "tag": "LECTURER",
                "icon": "fa-chalkboard-user",
                "color": "var(--color-primary-saddle)",
                "description": "Curriculum delivery and evaluation. Publish learning resources, author and grade assignments and quizzes, and monitor student workload.",
            },
            {
                "name": "Student",
                "tag": "STUDENT",
                "icon": "fa-user-graduate",
                "color": "var(--color-accent-caramel)",
                "description": "Active learning workspace. Access syllabus materials, submit coursework, take timed quizzes, track results, and optimize study schedules.",
            },
            {
                "name": "Parent",
                "tag": "PARENT",
                "icon": "fa-users-viewfinder",
                "color": "var(--color-accent-terracotta)",
                "description": "Observer portal with verified student linkage. View upcoming deadlines, submission statuses, and published grades for linked students.",
            },
        ],
    }
    return render(request, "core/index.html", context)


def dev_showcase_view(request: HttpRequest) -> HttpResponse:
    """Developer design-system and component showcase view (development use only)."""
    context = {
        "title": "Design System Showcase",
        "system_name": "Academic LMS Design Tokens",
        "phase_status": "Phase 8: Complete Integrated Scholastic LMS",
        "roles": [
            {
                "name": "Administrator",
                "tag": "ADMIN",
                "icon": "fa-shield-halved",
                "color": "var(--color-primary-espresso)",
                "description": "Systemic academic governance, user directory, program curricula, allocations, and institutional oversight.",
            },
            {
                "name": "Lecturer",
                "tag": "LECTURER",
                "icon": "fa-chalkboard-user",
                "color": "var(--color-primary-saddle)",
                "description": "Curriculum delivery, digital materials, assignments, rubric grading, quizzes, and class session attendance.",
            },
            {
                "name": "Student",
                "tag": "STUDENT",
                "icon": "fa-user-graduate",
                "color": "var(--color-accent-caramel)",
                "description": "Active coursework, submissions, quizzes, grades, attendance tracking, and the Smart Academic Workload Planner.",
            },
            {
                "name": "Parent",
                "tag": "PARENT",
                "icon": "fa-users-viewfinder",
                "color": "var(--color-accent-terracotta)",
                "description": "Strictly read-only observer visibility into attendance, published academic results, and deadline progress for linked students.",
            },
        ],
    }
    return render(request, "core/dev_showcase.html", context)


@login_required
def academic_calendar_view(request: HttpRequest) -> HttpResponse:
    """Consolidated interactive academic calendar with Month, Week, and List views."""
    user = request.user
    now = timezone.now()

    # 1. View Mode (month, week, list)
    view_mode = request.GET.get("view", "month")
    if view_mode not in ("month", "week", "list"):
        view_mode = "month"

    # 2. Date Navigation Parameters
    try:
        cur_year = int(request.GET.get("year", now.year))
        cur_month = int(request.GET.get("month", now.month))
        if cur_month < 1 or cur_month > 12:
            cur_month = now.month
    except (ValueError, TypeError):
        cur_year = now.year
        cur_month = now.month

    # 3. Filtering by Type and Course
    event_type = request.GET.get("type", "ALL")
    course_id_raw = request.GET.get("course")
    course_id = int(course_id_raw) if course_id_raw and course_id_raw.isdigit() else None

    # Parent target student picker
    target_student_id_raw = request.GET.get("student_id")
    target_student_id = int(target_student_id_raw) if target_student_id_raw and target_student_id_raw.isdigit() else None

    # Fetch events
    events = CalendarService.get_user_events(
        user=user,
        target_student_id=target_student_id,
        course_id=course_id,
        event_type_filter=event_type,
    )

    # 4. Generate View-Specific Data
    month_grid = []
    week_days = []
    month_name = calendar.month_name[cur_month]

    # Prev / Next month calculations
    prev_month = cur_month - 1 if cur_month > 1 else 12
    prev_year = cur_year if cur_month > 1 else cur_year - 1
    next_month = cur_month + 1 if cur_month < 12 else 1
    next_year = cur_year if cur_month < 12 else cur_year + 1

    if view_mode == "month":
        month_grid = CalendarService.build_month_grid(cur_year, cur_month, items=events)

    elif view_mode == "week":
        # 7-day window around current date
        start_of_week = now.date() - timedelta(days=now.date().weekday())  # Monday
        for d_offset in range(7):
            d = start_of_week + timedelta(days=d_offset)
            day_events = [
                ev for ev in events
                if ev.start_date.date() == d
                or (ev.end_date and ev.start_date.date() <= d <= ev.end_date.date())
            ]
            week_days.append({
                "date": d,
                "weekday_name": calendar.day_name[d.weekday()],
                "is_today": (d == now.date()),
                "events": day_events,
            })

    # Available Courses for filter dropdown
    filter_courses = []
    if getattr(user, "is_admin_role", False) or user.is_superuser:
        filter_courses = Course.objects.filter(is_active=True).order_by("code")
    elif getattr(user, "is_lecturer_role", False):
        filter_courses = Course.objects.filter(
            allocations__lecturer=user,
            allocations__is_active=True,
            is_active=True,
        ).distinct().order_by("code")
    elif getattr(user, "is_student_role", False):
        filter_courses = Course.objects.filter(
            enrollments__student=user,
            enrollments__status="ENROLLED",
            enrollments__is_active=True,
            is_active=True,
        ).distinct().order_by("code")
    elif getattr(user, "is_parent_role", False):
        linked_ids = ParentStudentRelationship.objects.filter(parent=user).values_list("student_id", flat=True)
        filter_courses = Course.objects.filter(
            enrollments__student_id__in=linked_ids,
            enrollments__status="ENROLLED",
            enrollments__is_active=True,
            is_active=True,
        ).distinct().order_by("code")

    # Parent linked students
    linked_children = []
    active_student = None
    if getattr(user, "is_parent_role", False):
        linked_children = ParentStudentRelationship.objects.filter(parent=user).select_related("student")
        # Resolve active_student from ?student_id= — verify the student is actually linked
        verified_linked_ids = set(linked_children.values_list("student_id", flat=True))
        if target_student_id and target_student_id in verified_linked_ids:
            active_student = next(
                (rel.student for rel in linked_children if rel.student_id == target_student_id),
                None,
            )
        elif linked_children:
            # Fall back to first linked child
            active_student = linked_children.first().student

    context = {
        "title": "Academic Calendar",
        "view_mode": view_mode,
        "cur_year": cur_year,
        "cur_month": cur_month,
        "month_name": month_name,
        "prev_year": prev_year,
        "prev_month": prev_month,
        "next_year": next_year,
        "next_month": next_month,
        "event_type": event_type,
        "course_id": course_id,
        "events": events,
        "month_grid": month_grid,
        "week_days": week_days,
        "filter_courses": filter_courses,
        "linked_children": linked_children,
        "active_student": active_student,
        "target_student_id": target_student_id,
    }
    return render(request, "core/calendar.html", context)
