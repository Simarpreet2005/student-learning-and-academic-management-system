from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils.translation import gettext_lazy as _

from accounts.decorators import admin_required, lecturer_required
from accounts.models import User, Student
from assignment.models import Assignment, AssignmentSubmission
from course.models import Course, CourseAllocation
from result.models import TakenCourse
from .forms import SessionForm, SemesterForm, NewsAndEventsForm
from .models import NewsAndEvents, ActivityLog, Session, Semester, Notification


# ########################################################
# News & Events & Dashboard Overview
# ########################################################
@login_required
def home_view(request):
    items = NewsAndEvents.objects.all().order_by("-updated_date")
    context = {
        "title": "News & Events",
        "items": items,
    }

    if request.user.is_student:
        enrolled_course_ids = TakenCourse.objects.filter(
            student__student=request.user
        ).values_list("course_id", flat=True)

        student_assignments = Assignment.objects.filter(
            course_id__in=enrolled_course_ids
        ).select_related("course").order_by("due_date")

        submissions = AssignmentSubmission.objects.filter(
            student__student=request.user
        ).select_related("assignment")
        submissions_map = {sub.assignment_id: sub for sub in submissions}

        assignment_list = []
        pending_count = 0
        submitted_count = 0
        graded_count = 0

        for a in student_assignments:
            sub = submissions_map.get(a.id)
            if sub:
                if sub.status == "graded":
                    graded_count += 1
                else:
                    submitted_count += 1
            else:
                if not a.is_closed:
                    pending_count += 1
            assignment_list.append({"assignment": a, "submission": sub})

        context.update(
            {
                "student_assignments": assignment_list[:5],
                "total_student_assignments": len(assignment_list),
                "pending_assignments_count": pending_count,
                "submitted_assignments_count": submitted_count,
                "graded_assignments_count": graded_count,
                "is_student": True,
            }
        )

    elif request.user.is_lecturer or request.user.is_superuser:
        if request.user.is_superuser:
            allocated_course_ids = Course.objects.values_list("id", flat=True)
        else:
            allocated_course_ids = CourseAllocation.objects.filter(
                lecturer=request.user
            ).values_list("courses", flat=True)

        lecturer_assignments = Assignment.objects.filter(
            course_id__in=allocated_course_ids
        ).select_related("course").order_by("-created_at")

        awaiting_grading = AssignmentSubmission.objects.filter(
            assignment__course_id__in=allocated_course_ids,
            marks__isnull=True,
        ).select_related("assignment__course", "student__student").order_by("submitted_at")

        total_submissions = AssignmentSubmission.objects.filter(
            assignment__course_id__in=allocated_course_ids
        ).count()
        total_graded = AssignmentSubmission.objects.filter(
            assignment__course_id__in=allocated_course_ids,
            marks__isnull=False,
        ).count()

        assignment_list = []
        for a in lecturer_assignments[:5]:
            sub_count = a.submissions.count()
            graded_c = a.submissions.filter(marks__isnull=False).count()
            assignment_list.append(
                {
                    "assignment": a,
                    "total_submissions": sub_count,
                    "total_graded": graded_c,
                    "pending_grading": sub_count - graded_c,
                }
            )

        context.update(
            {
                "lecturer_assignments": assignment_list,
                "awaiting_grading_submissions": awaiting_grading[:5],
                "total_lecturer_assignments": lecturer_assignments.count(),
                "total_submissions_count": total_submissions,
                "total_pending_grading_count": awaiting_grading.count(),
                "total_graded_count": total_graded,
                "is_lecturer": True,
            }
        )

    return render(request, "core/index.html", context)


@login_required
@admin_required
def dashboard_view(request):
    logs = ActivityLog.objects.all().order_by("-created_at")[:10]
    gender_count = Student.get_gender_count()
    context = {
        "student_count": User.objects.get_student_count(),
        "lecturer_count": User.objects.get_lecturer_count(),
        "superuser_count": User.objects.get_superuser_count(),
        "males_count": gender_count["M"],
        "females_count": gender_count["F"],
        "logs": logs,
        "total_assignments": Assignment.objects.count(),
        "total_submissions": AssignmentSubmission.objects.count(),
        "total_pending_grading": AssignmentSubmission.objects.filter(marks__isnull=True).count(),
    }
    return render(request, "core/dashboard.html", context)


@login_required
@lecturer_required
def post_add(request):
    if request.method == "POST":
        form = NewsAndEventsForm(request.POST)
        title = form.cleaned_data.get("title", "Post") if form.is_valid() else None
        if form.is_valid():
            form.save()
            messages.success(request, f"{title} has been uploaded.")
            return redirect("home")
        messages.error(request, "Please correct the error(s) below.")
    else:
        form = NewsAndEventsForm()
    return render(request, "core/post_add.html", {"title": "Add Post", "form": form})


@login_required
@lecturer_required
def edit_post(request, pk):
    instance = get_object_or_404(NewsAndEvents, pk=pk)
    if request.method == "POST":
        form = NewsAndEventsForm(request.POST, instance=instance)
        title = form.cleaned_data.get("title", "Post") if form.is_valid() else None
        if form.is_valid():
            form.save()
            messages.success(request, f"{title} has been updated.")
            return redirect("home")
        messages.error(request, "Please correct the error(s) below.")
    else:
        form = NewsAndEventsForm(instance=instance)
    return render(request, "core/post_add.html", {"title": "Edit Post", "form": form})


@login_required
@lecturer_required
def delete_post(request, pk):
    post = get_object_or_404(NewsAndEvents, pk=pk)
    post_title = post.title
    post.delete()
    messages.success(request, f"{post_title} has been deleted.")
    return redirect("home")


# ########################################################
# Session
# ########################################################
@login_required
@lecturer_required
def session_list_view(request):
    """Show list of all sessions"""
    sessions = Session.objects.all().order_by("-is_current_session", "-session")
    return render(request, "core/session_list.html", {"sessions": sessions})


@login_required
@lecturer_required
def session_add_view(request):
    """Add a new session"""
    if request.method == "POST":
        form = SessionForm(request.POST)
        if form.is_valid():
            if form.cleaned_data.get("is_current_session"):
                unset_current_session()
            form.save()
            messages.success(request, "Session added successfully.")
            return redirect("session_list")
    else:
        form = SessionForm()
    return render(request, "core/session_update.html", {"form": form})


@login_required
@lecturer_required
def session_update_view(request, pk):
    session = get_object_or_404(Session, pk=pk)
    if request.method == "POST":
        form = SessionForm(request.POST, instance=session)
        if form.is_valid():
            if form.cleaned_data.get("is_current_session"):
                unset_current_session()
            form.save()
            messages.success(request, "Session updated successfully.")
            return redirect("session_list")
    else:
        form = SessionForm(instance=session)
    return render(request, "core/session_update.html", {"form": form})


@login_required
@lecturer_required
def session_delete_view(request, pk):
    session = get_object_or_404(Session, pk=pk)
    if session.is_current_session:
        messages.error(request, "You cannot delete the current session.")
    else:
        session.delete()
        messages.success(request, "Session successfully deleted.")
    return redirect("session_list")


def unset_current_session():
    """Unset current session"""
    current_session = Session.objects.filter(is_current_session=True).first()
    if current_session:
        current_session.is_current_session = False
        current_session.save()


# ########################################################
# Semester
# ########################################################
@login_required
@lecturer_required
def semester_list_view(request):
    semesters = Semester.objects.all().order_by("-is_current_semester", "-semester")
    return render(request, "core/semester_list.html", {"semesters": semesters})


@login_required
@lecturer_required
def semester_add_view(request):
    if request.method == "POST":
        form = SemesterForm(request.POST)
        if form.is_valid():
            if form.cleaned_data.get("is_current_semester"):
                unset_current_semester()
                unset_current_session()
            form.save()
            messages.success(request, "Semester added successfully.")
            return redirect("semester_list")
    else:
        form = SemesterForm()
    return render(request, "core/semester_update.html", {"form": form})


@login_required
@lecturer_required
def semester_update_view(request, pk):
    semester = get_object_or_404(Semester, pk=pk)
    if request.method == "POST":
        form = SemesterForm(request.POST, instance=semester)
        if form.is_valid():
            if form.cleaned_data.get("is_current_semester"):
                unset_current_semester()
                unset_current_session()
            form.save()
            messages.success(request, "Semester updated successfully!")
            return redirect("semester_list")
    else:
        form = SemesterForm(instance=semester)
    return render(request, "core/semester_update.html", {"form": form})


@login_required
@lecturer_required
def semester_delete_view(request, pk):
    semester = get_object_or_404(Semester, pk=pk)
    if semester.is_current_semester:
        messages.error(request, "You cannot delete the current semester.")
    else:
        semester.delete()
        messages.success(request, "Semester successfully deleted.")
    return redirect("semester_list")


def unset_current_semester():
    """Unset current semester"""
    current_semester = Semester.objects.filter(is_current_semester=True).first()
    if current_semester:
        current_semester.is_current_semester = False
        current_semester.save()


# ########################################################
# Notifications
# ########################################################
@login_required
def notification_list(request):
    """View notifications for the logged-in user."""
    notifications = Notification.objects.filter(
        user=request.user
    ).order_by("-created_at")
    unread_count = notifications.filter(is_read=False).count()
    context = {
        "title": _("Notifications"),
        "notifications": notifications,
        "unread_count": unread_count,
    }
    return render(request, "core/notification_list.html", context)


@login_required
def mark_notification_read(request, pk):
    """Mark a single notification as read and navigate to its link."""
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    notification.mark_as_read()
    if notification.link:
        return redirect(notification.link)
    return redirect("notification_list")


@login_required
def mark_all_notifications_read(request):
    """Mark all unread notifications for the current user as read."""
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    messages.success(request, _("All notifications marked as read."))
    return redirect("notification_list")
