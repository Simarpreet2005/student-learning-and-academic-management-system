"""Authentication, profile, and authorization views for Academic LMS."""
from django.contrib import messages
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import (
    PasswordChangeView,
    PasswordResetView,
    PasswordResetDoneView,
    PasswordResetConfirmView,
    PasswordResetCompleteView,
)
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from apps.academics.models import (
    AcademicProgram,
    AcademicYear,
    Course,
    CourseAllocation,
    Department,
    EnrollmentStatus,
    Semester,
    StudentEnrollment,
)
from apps.assessments.models import Assignment, AssignmentSubmission
from apps.core.models import AcademicEvent
from apps.courseware.models import LearningResource, ResourceStatus
from apps.planner.services import WorkloadPlannerService
from apps.quizzes.models import AttemptStatus, Quiz, QuizAttempt, QuizStatus

from .forms import (
    LoginForm,
    UserProfileUpdateForm,
    StudentProfileUpdateForm,
    LecturerProfileUpdateForm,
    ParentProfileUpdateForm,
    ParentStudentRelationshipForm,
)
from .models import (
    User,
    Role,
    StudentProfile,
    LecturerProfile,
    ParentProfile,
    ParentStudentRelationship,
)
from .permissions import (
    admin_required,
    lecturer_required,
    student_required,
    parent_required,
    can_view_student_data,
    can_edit_profile,
)


def get_dashboard_url_for_user(user: User) -> str:
    """Return the canonical role-specific dashboard URL for the authenticated user."""
    if user.is_superuser or user.is_staff or user.role == Role.ADMIN:
        return reverse("accounts:admin_dashboard")
    elif user.role == Role.LECTURER:
        return reverse("accounts:lecturer_dashboard")
    elif user.role == Role.STUDENT:
        return reverse("accounts:student_dashboard")
    elif user.role == Role.PARENT:
        return reverse("accounts:parent_dashboard")
    return reverse("core:index")


# ==============================================================================
# Authentication Views
# ==============================================================================

def login_view(request: HttpRequest) -> HttpResponse:
    """Handle user authentication via email and password."""
    if request.user.is_authenticated:
        return redirect(get_dashboard_url_for_user(request.user))

    redirect_to = request.GET.get("next", "")

    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            user = form.get_user()
            auth_login(request, user)
            messages.success(request, f"Welcome back, {user.get_full_name}!")

            # Validate next URL against open redirect vulnerabilities
            if redirect_to and url_has_allowed_host_and_scheme(
                redirect_to, allowed_hosts={request.get_host()}
            ):
                return redirect(redirect_to)

            return redirect(get_dashboard_url_for_user(user))
    else:
        form = LoginForm()

    return render(
        request,
        "accounts/login.html",
        {
            "form": form,
            "title": "Sign In to Academic LMS",
            "next": redirect_to,
        },
    )


def logout_view(request: HttpRequest) -> HttpResponse:
    """Safely log out the authenticated user."""
    if request.user.is_authenticated:
        auth_logout(request)
        messages.info(request, "You have been successfully signed out.")
    return redirect("accounts:login")


def access_denied_view(request: HttpRequest, exception=None) -> HttpResponse:
    """Render a styled HTTP 403 Access Denied page in the brown-and-cream theme."""
    return render(
        request,
        "accounts/access_denied.html",
        {"title": "Access Denied | Academic LMS"},
        status=403,
    )


# ==============================================================================
# Role-Specific Dashboards
# ==============================================================================

@login_required
@admin_required
def admin_dashboard_view(request: HttpRequest) -> HttpResponse:
    """Administrator Command Center with system-wide academic metrics and activity tracking."""
    # User and role metrics
    total_users = User.objects.count()
    student_count = User.objects.filter(role=Role.STUDENT).count()
    lecturer_count = User.objects.filter(role=Role.LECTURER).count()
    parent_count = User.objects.filter(role=Role.PARENT).count()
    admin_count = User.objects.filter(role=Role.ADMIN).count()
    relationships_count = ParentStudentRelationship.objects.count()

    # Academic Structure metrics
    department_count = Department.objects.count()
    program_count = AcademicProgram.objects.count()
    academic_year_count = AcademicYear.objects.count()
    semester_count = Semester.objects.count()

    # Course & Enrollment metrics
    course_count = Course.objects.count()
    allocation_count = CourseAllocation.objects.filter(is_active=True).count()
    enrollment_count = StudentEnrollment.objects.filter(
        status=EnrollmentStatus.ENROLLED, is_active=True
    ).count()

    # Assessment & Grading metrics
    assignment_count = Assignment.objects.count()
    submission_count = AssignmentSubmission.objects.count()
    pending_assignments_count = AssignmentSubmission.objects.filter(
        status=AssignmentSubmission.SubmissionStatus.SUBMITTED, is_active=True
    ).count()
    quiz_count = Quiz.objects.count()
    attempt_count = QuizAttempt.objects.count()
    pending_quizzes_count = QuizAttempt.objects.filter(
        status=AttemptStatus.SUBMITTED
    ).count()

    # Recent academic events
    now = timezone.now()
    recent_events = AcademicEvent.objects.order_by("-start_date")[:5]

    context = {
        "title": "Administrator Dashboard",
        "total_users": total_users,
        "student_count": student_count,
        "lecturer_count": lecturer_count,
        "parent_count": parent_count,
        "admin_count": admin_count,
        "relationships_count": relationships_count,
        "department_count": department_count,
        "program_count": program_count,
        "academic_year_count": academic_year_count,
        "semester_count": semester_count,
        "course_count": course_count,
        "allocation_count": allocation_count,
        "enrollment_count": enrollment_count,
        "assignment_count": assignment_count,
        "submission_count": submission_count,
        "pending_assignments_count": pending_assignments_count,
        "quiz_count": quiz_count,
        "attempt_count": attempt_count,
        "pending_quizzes_count": pending_quizzes_count,
        "recent_events": recent_events,
    }
    return render(request, "accounts/dashboards/admin.html", context)


@login_required
@lecturer_required
def lecturer_dashboard_view(request: HttpRequest) -> HttpResponse:
    """Lecturer Instructional Hub with courses, pending grading queues, and workload alerts."""
    lecturer_profile, _ = LecturerProfile.objects.get_or_create(
        user=request.user,
        defaults={"employee_id": f"LEC-{request.user.id:04d}"},
    )
    now = timezone.now()

    # Lecturer's allocated courses
    allocations = (
        CourseAllocation.objects.filter(lecturer=request.user, is_active=True)
        .select_related("course", "course__department", "semester")
        .order_by("course__code")
    )
    course_ids = [a.course_id for a in allocations]

    # Total unique students enrolled in lecturer's courses
    total_students_enrolled = (
        StudentEnrollment.objects.filter(
            course_id__in=course_ids,
            status=EnrollmentStatus.ENROLLED,
            is_active=True,
        )
        .values("student_id")
        .distinct()
        .count()
    )

    # Deliverables & Quizzes
    upcoming_assignments = (
        Assignment.objects.filter(course_id__in=course_ids, is_active=True)
        .select_related("course")
        .order_by("-created_at")[:5]
    )
    upcoming_quizzes = (
        Quiz.objects.filter(course_id__in=course_ids, is_active=True)
        .select_related("course")
        .order_by("-created_at")[:5]
    )

    # Pending grading queues
    pending_assignment_submissions = (
        AssignmentSubmission.objects.filter(
            assignment__course_id__in=course_ids,
            status=AssignmentSubmission.SubmissionStatus.SUBMITTED,
            is_active=True,
        )
        .select_related("assignment", "assignment__course", "student")
        .order_by("submitted_at")
    )
    pending_assignments_count = pending_assignment_submissions.count()
    pending_assignments_preview = pending_assignment_submissions[:5]

    pending_quiz_attempts = (
        QuizAttempt.objects.filter(
            quiz__course_id__in=course_ids,
            status=AttemptStatus.SUBMITTED,
        )
        .select_related("quiz", "quiz__course", "student")
        .order_by("submitted_at")
    )
    pending_quizzes_count = pending_quiz_attempts.count()
    pending_quizzes_preview = pending_quiz_attempts[:5]

    total_grading_pending = pending_assignments_count + pending_quizzes_count

    # Course workload summaries
    course_summaries = []
    for alloc in allocations:
        workload_data = WorkloadPlannerService.get_course_workload(
            course=alloc.course, reference_time=now
        )
        course_summaries.append({
            "allocation": alloc,
            "workload": workload_data,
        })

    # Academic events
    upcoming_events = (
        AcademicEvent.objects.filter(is_published=True, start_date__gte=now)
        .order_by("start_date")[:5]
    )

    context = {
        "title": "Lecturer Dashboard",
        "profile": lecturer_profile,
        "allocations": allocations,
        "course_ids": course_ids,
        "total_courses": len(allocations),
        "total_students_enrolled": total_students_enrolled,
        "upcoming_assignments": upcoming_assignments,
        "upcoming_quizzes": upcoming_quizzes,
        "pending_assignments_count": pending_assignments_count,
        "pending_assignments_preview": pending_assignments_preview,
        "pending_quizzes_count": pending_quizzes_count,
        "pending_quizzes_preview": pending_quizzes_preview,
        "total_grading_pending": total_grading_pending,
        "course_summaries": course_summaries,
        "upcoming_events": upcoming_events,
    }
    return render(request, "accounts/dashboards/lecturer.html", context)


@login_required
@student_required
def student_dashboard_view(request: HttpRequest) -> HttpResponse:
    """Student Academic & Planning Center."""
    student_profile, _ = StudentProfile.objects.get_or_create(
        user=request.user,
        defaults={"student_id": f"STD-{request.user.id:04d}"},
    )
    now = timezone.now()

    # Enrolled courses
    enrollments = (
        StudentEnrollment.objects.filter(
            student=request.user,
            status=EnrollmentStatus.ENROLLED,
            is_active=True,
        )
        .select_related("course", "course__department", "semester")
        .order_by("course__code")
    )
    course_ids = [e.course_id for e in enrollments]

    # Published learning materials
    recent_resources = (
        LearningResource.objects.filter(
            course_id__in=course_ids,
            status=ResourceStatus.PUBLISHED,
        )
        .select_related("course", "module")
        .order_by("-created_at")[:5]
    )

    # Upcoming assignments
    upcoming_assignments = (
        Assignment.objects.filter(
            course_id__in=course_ids,
            is_published=True,
            is_active=True,
            due_date__gte=now,
        )
        .select_related("course")
        .order_by("due_date")[:5]
    )

    # Upcoming quizzes
    upcoming_quizzes = (
        Quiz.objects.filter(
            course_id__in=course_ids,
            status=QuizStatus.PUBLISHED,
            is_active=True,
            available_to__gte=now,
        )
        .select_related("course")
        .order_by("available_to")[:5]
    )

    # Recent assignment submissions
    recent_submissions = (
        AssignmentSubmission.objects.filter(student=request.user, is_active=True)
        .select_related("assignment", "assignment__course")
        .order_by("-submitted_at")[:5]
    )

    # Recent completed quiz results
    recent_quiz_results = (
        QuizAttempt.objects.filter(
            student=request.user,
            status=AttemptStatus.COMPLETED,
        )
        .select_related("quiz", "quiz__course")
        .order_by("-submitted_at")[:5]
    )

    # Workload summary
    try:
        workload = WorkloadPlannerService.get_student_workload(
            student=request.user, reference_time=now
        )
    except Exception:
        workload = None

    # Academic events
    upcoming_events = (
        AcademicEvent.objects.filter(is_published=True, start_date__gte=now)
        .order_by("start_date")[:5]
    )

    context = {
        "title": "Student Dashboard",
        "profile": student_profile,
        "enrollments": enrollments,
        "enrolled_courses_count": len(enrollments),
        "recent_resources": recent_resources,
        "upcoming_assignments": upcoming_assignments,
        "upcoming_quizzes": upcoming_quizzes,
        "recent_submissions": recent_submissions,
        "recent_quiz_results": recent_quiz_results,
        "workload": workload,
        "upcoming_events": upcoming_events,
    }
    return render(request, "accounts/dashboards/student.html", context)


@login_required
@parent_required
def parent_dashboard_view(request: HttpRequest) -> HttpResponse:
    """Parent Observer Portal with multi-child switcher, deadline progress, and permitted results."""
    parent_profile, _ = ParentProfile.objects.get_or_create(user=request.user)
    now = timezone.now()

    # Strictly fetch only linked students
    relationships = (
        ParentStudentRelationship.objects.filter(parent=request.user)
        .select_related("student", "student__student_profile")
        .order_by("student__first_name", "student__last_name")
    )

    selected_student = None
    selected_rel = None
    student_id_param = request.GET.get("student_id")

    if relationships.exists():
        if student_id_param:
            try:
                sid = int(student_id_param)
                for rel in relationships:
                    if rel.student_id == sid:
                        selected_student = rel.student
                        selected_rel = rel
                        break
            except (ValueError, TypeError):
                pass

        # Fallback to first linked student if none selected or invalid ID passed
        if not selected_student:
            selected_rel = relationships.first()
            selected_student = selected_rel.student

    student_enrollments = []
    upcoming_assignments = []
    upcoming_quizzes = []
    recent_submissions = []
    recent_quiz_results = []
    workload = None

    if selected_student:
        student_enrollments = (
            StudentEnrollment.objects.filter(
                student=selected_student,
                status=EnrollmentStatus.ENROLLED,
                is_active=True,
            )
            .select_related("course", "course__department", "semester")
            .order_by("course__code")
        )
        course_ids = [e.course_id for e in student_enrollments]

        upcoming_assignments = (
            Assignment.objects.filter(
                course_id__in=course_ids,
                is_published=True,
                is_active=True,
                due_date__gte=now,
            )
            .select_related("course")
            .order_by("due_date")[:5]
        )

        upcoming_quizzes = (
            Quiz.objects.filter(
                course_id__in=course_ids,
                status=QuizStatus.PUBLISHED,
                is_active=True,
                available_to__gte=now,
            )
            .select_related("course")
            .order_by("available_to")[:5]
        )

        recent_submissions = (
            AssignmentSubmission.objects.filter(
                student=selected_student, is_active=True
            )
            .select_related("assignment", "assignment__course")
            .order_by("-submitted_at")[:5]
        )

        recent_quiz_results = (
            QuizAttempt.objects.filter(
                student=selected_student,
                status=AttemptStatus.COMPLETED,
            )
            .select_related("quiz", "quiz__course")
            .order_by("-submitted_at")[:5]
        )

        try:
            workload = WorkloadPlannerService.get_student_workload(
                student=selected_student, reference_time=now
            )
        except Exception:
            workload = None

    # Academic events
    upcoming_events = (
        AcademicEvent.objects.filter(is_published=True, start_date__gte=now)
        .order_by("start_date")[:5]
    )

    context = {
        "title": "Parent Portal",
        "profile": parent_profile,
        "linked_students": relationships,
        "selected_student": selected_student,
        "selected_rel": selected_rel,
        "student_enrollments": student_enrollments,
        "upcoming_assignments": upcoming_assignments,
        "upcoming_quizzes": upcoming_quizzes,
        "recent_submissions": recent_submissions,
        "recent_quiz_results": recent_quiz_results,
        "workload": workload,
        "upcoming_events": upcoming_events,
    }
    return render(request, "accounts/dashboards/parent.html", context)
    return render(request, "accounts/dashboards/parent.html", context)


# ==============================================================================
# User Profile Views & Permitted Editing
# ==============================================================================

@login_required
def profile_view(request: HttpRequest) -> HttpResponse:
    """View personal profile details and role-specific metadata."""
    user = request.user
    context = {
        "title": f"Profile — {user.get_full_name}",
        "profile_user": user,
    }

    if user.is_student_role:
        profile, _ = StudentProfile.objects.get_or_create(
            user=user,
            defaults={"student_id": f"STD-{user.id:04d}"},
        )
        context["student_profile"] = profile
    elif user.is_lecturer_role:
        profile, _ = LecturerProfile.objects.get_or_create(
            user=user,
            defaults={"employee_id": f"LEC-{user.id:04d}"},
        )
        context["lecturer_profile"] = profile
    elif user.is_parent_role:
        profile, _ = ParentProfile.objects.get_or_create(user=user)
        context["parent_profile"] = profile
        context["linked_students"] = ParentStudentRelationship.objects.filter(
            parent=user
        ).select_related("student", "student__student_profile")

    return render(request, "accounts/profile.html", context)


@login_required
def profile_edit_view(request: HttpRequest) -> HttpResponse:
    """Allow user to edit permitted personal and profile details.

    Explicitly prevents role escalation or role modification.
    """
    user = request.user
    role_form = None

    if user.is_student_role:
        profile, _ = StudentProfile.objects.get_or_create(
            user=user,
            defaults={"student_id": f"STD-{user.id:04d}"},
        )
        profile_form_class = StudentProfileUpdateForm
    elif user.is_lecturer_role:
        profile, _ = LecturerProfile.objects.get_or_create(
            user=user,
            defaults={"employee_id": f"LEC-{user.id:04d}"},
        )
        profile_form_class = LecturerProfileUpdateForm
    elif user.is_parent_role:
        profile, _ = ParentProfile.objects.get_or_create(user=user)
        profile_form_class = ParentProfileUpdateForm
    else:
        profile = None
        profile_form_class = None

    if request.method == "POST":
        user_form = UserProfileUpdateForm(request.POST, instance=user)
        if profile and profile_form_class:
            role_form = profile_form_class(request.POST, instance=profile)
            if user_form.is_valid() and role_form.is_valid():
                user_form.save()
                role_form.save()
                messages.success(request, "Your profile has been updated successfully.")
                return redirect("accounts:profile")
        else:
            if user_form.is_valid():
                user_form.save()
                messages.success(request, "Your profile has been updated successfully.")
                return redirect("accounts:profile")
    else:
        user_form = UserProfileUpdateForm(instance=user)
        if profile and profile_form_class:
            role_form = profile_form_class(instance=profile)

    context = {
        "title": "Edit Profile | Academic LMS",
        "user_form": user_form,
        "role_form": role_form,
    }
    return render(request, "accounts/profile_edit.html", context)


@login_required
def student_detail_view(request: HttpRequest, student_id: int) -> HttpResponse:
    """Authorized view for inspecting a student's profile.

    Enforces strict object-level authorization:
    - Admin can view.
    - The student themselves can view.
    - A Parent linked via ParentStudentRelationship can view.
    - Any other user receives HTTP 403 Forbidden.
    """
    target_student = get_object_or_404(User, pk=student_id, role=Role.STUDENT)

    if not can_view_student_data(request.user, target_student):
        raise PermissionDenied("You do not have authorized permission to view this student's records.")

    student_profile, _ = StudentProfile.objects.get_or_create(
        user=target_student,
        defaults={"student_id": f"STD-{target_student.id:04d}"},
    )

    # If viewer is a parent, determine relationship type
    relationship = None
    if request.user.is_parent_role:
        relationship = ParentStudentRelationship.objects.filter(
            parent=request.user,
            student=target_student,
        ).first()

    context = {
        "title": f"Student Record: {target_student.get_full_name}",
        "student_user": target_student,
        "student_profile": student_profile,
        "relationship": relationship,
    }
    return render(request, "accounts/student_detail.html", context)


# ==============================================================================
# Administrator: Parent-Student Linkage Management
# ==============================================================================

@login_required
@admin_required
def admin_relationship_list_view(request: HttpRequest) -> HttpResponse:
    """Administrator view of all parent-student linkages."""
    relationships = ParentStudentRelationship.objects.select_related(
        "parent", "student", "student__student_profile"
    ).all()
    context = {
        "title": "Parent–Student Linkages",
        "relationships": relationships,
    }
    return render(request, "accounts/relationships/list.html", context)


@login_required
@admin_required
def admin_relationship_create_view(request: HttpRequest) -> HttpResponse:
    """Administrator view to link a parent and student account."""
    if request.method == "POST":
        form = ParentStudentRelationshipForm(request.POST)
        if form.is_valid():
            rel = form.save()
            messages.success(
                request,
                f"Successfully linked {rel.parent.get_full_name} to {rel.student.get_full_name} as {rel.get_relationship_type_display()}."
            )
            return redirect("accounts:admin_relationship_list")
    else:
        form = ParentStudentRelationshipForm()

    context = {
        "title": "Link Parent & Student",
        "form": form,
    }
    return render(request, "accounts/relationships/create.html", context)


@login_required
@admin_required
def admin_relationship_delete_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Administrator view to remove a parent-student linkage."""
    relationship = get_object_or_404(ParentStudentRelationship, pk=pk)
    if request.method == "POST":
        parent_name = relationship.parent.get_full_name
        student_name = relationship.student.get_full_name
        relationship.delete()
        messages.success(
            request,
            f"Removed relationship between {parent_name} and {student_name}."
        )
        return redirect("accounts:admin_relationship_list")

    context = {
        "title": "Confirm Removal of Relationship",
        "relationship": relationship,
    }
    return render(request, "accounts/relationships/delete_confirm.html", context)


# ==============================================================================
# Password Management (Subclassing Django Built-in Auth Views)
# ==============================================================================

class CustomPasswordChangeView(PasswordChangeView):
    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("accounts:profile")

    def form_valid(self, form):
        messages.success(self.request, "Your password has been changed successfully.")
        return super().form_valid(form)


class CustomPasswordResetView(PasswordResetView):
    template_name = "accounts/password_reset.html"
    email_template_name = "accounts/emails/password_reset_email.html"
    subject_template_name = "accounts/emails/password_reset_subject.txt"
    success_url = reverse_lazy("accounts:password_reset_done")


class CustomPasswordResetDoneView(PasswordResetDoneView):
    template_name = "accounts/password_reset_done.html"


class CustomPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = "accounts/password_reset_confirm.html"
    success_url = reverse_lazy("accounts:password_reset_complete")


class CustomPasswordResetCompleteView(PasswordResetCompleteView):
    template_name = "accounts/password_reset_complete.html"
