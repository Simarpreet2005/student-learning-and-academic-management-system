import os
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, HttpResponseForbidden, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from accounts.decorators import lecturer_required, student_required
from accounts.models import Student
from core.utils import notify_assignment_created, notify_assignment_graded
from course.models import Course, CourseAllocation
from result.models import TakenCourse

from .forms import (
    AssignmentForm,
    AssignmentSubmissionForm,
    SubmissionGradeForm,
)
from .models import Assignment, AssignmentSubmission


def is_course_lecturer(user, course):
    """Check if the user is a superuser or allocated lecturer for the course."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return CourseAllocation.objects.filter(courses=course, lecturer=user).exists()


def is_course_student(user, course):
    """Check if the user is a superuser or enrolled student in the course."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return TakenCourse.objects.filter(student__student=user, course=course).exists()


@login_required
def assignment_list(request, slug):
    """List all assignments for a specific course with role-specific views."""
    course = get_object_or_404(Course, slug=slug)

    # Permission check: User must be enrolled student or allocated lecturer or superuser
    is_lecturer = is_course_lecturer(request.user, course)
    is_student = is_course_student(request.user, course)

    if not (is_lecturer or is_student):
        messages.error(
            request, _("You do not have permission to view assignments for this course.")
        )
        return redirect("course_detail", slug=course.slug)

    assignments = Assignment.objects.filter(course=course).order_by("-due_date", "-created_at")

    # If student, attach submission status for each assignment
    student_submissions = {}
    if request.user.is_student:
        submissions = AssignmentSubmission.objects.filter(
            assignment__course=course, student__student=request.user
        )
        student_submissions = {sub.assignment_id: sub for sub in submissions}

    # If lecturer, attach submission count metrics
    assignment_data = []
    for assignment in assignments:
        item = {"assignment": assignment}
        if request.user.is_student:
            item["submission"] = student_submissions.get(assignment.id)
        else:
            total_submissions = assignment.submissions.count()
            graded_submissions = assignment.submissions.filter(marks__isnull=False).count()
            enrolled_count = TakenCourse.objects.filter(course=course).count()
            item["total_submissions"] = total_submissions
            item["graded_submissions"] = graded_submissions
            item["enrolled_count"] = enrolled_count
        assignment_data.append(item)

    context = {
        "title": f"Assignments - {course.code}",
        "course": course,
        "assignment_data": assignment_data,
        "is_lecturer": is_lecturer,
        "is_student": is_student,
    }
    return render(request, "assignment/assignment_list.html", context)


@login_required
@lecturer_required
def assignment_create(request, slug):
    """Create a new assignment for a course (lecturer/admin)."""
    course = get_object_or_404(Course, slug=slug)

    if not is_course_lecturer(request.user, course):
        messages.error(
            request, _("You are not authorized to create assignments for this course.")
        )
        return redirect("course_detail", slug=course.slug)

    if request.method == "POST":
        form = AssignmentForm(request.POST, request.FILES)
        if form.is_valid():
            assignment = form.save(commit=False)
            assignment.course = course
            assignment.created_by = request.user
            assignment.save()
            notify_assignment_created(assignment)
            messages.success(
                request, f"Assignment '{assignment.title}' created successfully!"
            )
            return redirect("assignment_detail", slug=assignment.slug)
        messages.error(request, _("Please correct the errors below."))
    else:
        form = AssignmentForm()

    context = {
        "title": f"Create Assignment - {course.code}",
        "form": form,
        "course": course,
    }
    return render(request, "assignment/assignment_form.html", context)


@login_required
def assignment_detail(request, slug):
    """View details of a specific assignment and student submission interface."""
    assignment = get_object_or_404(Assignment, slug=slug)
    course = assignment.course

    is_lecturer = is_course_lecturer(request.user, course)
    is_student = is_course_student(request.user, course)

    if not (is_lecturer or is_student):
        messages.error(
            request, _("You do not have permission to view this assignment.")
        )
        return redirect("home")

    submission = None
    submission_form = None

    if request.user.is_student:
        submission = AssignmentSubmission.objects.filter(
            assignment=assignment, student__student=request.user
        ).first()

        # Initialize submission form for student
        if not submission or assignment.allow_resubmission:
            submission_form = AssignmentSubmissionForm(instance=submission)

    # Calculate metrics for lecturer
    metrics = {}
    if is_lecturer:
        total_enrolled = TakenCourse.objects.filter(course=course).count()
        total_submitted = assignment.submissions.count()
        total_graded = assignment.submissions.filter(marks__isnull=False).count()
        metrics = {
            "total_enrolled": total_enrolled,
            "total_submitted": total_submitted,
            "total_graded": total_graded,
            "pending_grading": total_submitted - total_graded,
        }

    context = {
        "title": f"{assignment.title} - {course.code}",
        "assignment": assignment,
        "course": course,
        "submission": submission,
        "submission_form": submission_form,
        "is_lecturer": is_lecturer,
        "is_student": is_student,
        "metrics": metrics,
    }
    return render(request, "assignment/assignment_detail.html", context)


@login_required
@lecturer_required
def assignment_edit(request, slug):
    """Edit an existing assignment (allocated lecturer / admin)."""
    assignment = get_object_or_404(Assignment, slug=slug)
    course = assignment.course

    if not is_course_lecturer(request.user, course):
        messages.error(
            request, _("You are not authorized to edit this assignment.")
        )
        return redirect("assignment_detail", slug=assignment.slug)

    if request.method == "POST":
        form = AssignmentForm(request.POST, request.FILES, instance=assignment)
        if form.is_valid():
            form.save()
            messages.success(
                request, f"Assignment '{assignment.title}' updated successfully!"
            )
            return redirect("assignment_detail", slug=assignment.slug)
        messages.error(request, _("Please correct the errors below."))
    else:
        form = AssignmentForm(instance=assignment)

    context = {
        "title": f"Edit Assignment - {assignment.title}",
        "form": form,
        "course": course,
        "assignment": assignment,
    }
    return render(request, "assignment/assignment_form.html", context)


@login_required
@lecturer_required
def assignment_delete(request, slug):
    """Delete an assignment and associated files."""
    assignment = get_object_or_404(Assignment, slug=slug)
    course = assignment.course

    if not is_course_lecturer(request.user, course):
        messages.error(
            request, _("You are not authorized to delete this assignment.")
        )
        return redirect("assignment_detail", slug=assignment.slug)

    course_slug = course.slug
    title = assignment.title
    assignment.delete()
    messages.success(request, f"Assignment '{title}' was deleted successfully.")
    return redirect("assignment_list", slug=course_slug)


@login_required
@student_required
def assignment_submit(request, slug):
    """Submit or resubmit an assignment file (student only)."""
    if request.method != "POST":
        return redirect("assignment_detail", slug=slug)

    assignment = get_object_or_404(Assignment, slug=slug)
    course = assignment.course

    if not is_course_student(request.user, course):
        messages.error(
            request, _("You are not enrolled in the course for this assignment.")
        )
        return redirect("home")

    student = get_object_or_404(Student, student=request.user)
    submission = AssignmentSubmission.objects.filter(
        assignment=assignment, student=student
    ).first()

    # Verify if assignment is open
    if assignment.is_upcoming:
        messages.error(
            request,
            _("This assignment is upcoming and not yet open for submissions."),
        )
        return redirect("assignment_detail", slug=assignment.slug)

    # Verify resubmission policy
    if submission and not assignment.allow_resubmission:
        messages.error(
            request,
            _("Resubmissions are not permitted for this assignment."),
        )
        return redirect("assignment_detail", slug=assignment.slug)

    form = AssignmentSubmissionForm(request.POST, request.FILES, instance=submission)
    if form.is_valid():
        sub = form.save(commit=False)
        sub.assignment = assignment
        sub.student = student

        # Check if submission is late
        if timezone.now() > assignment.due_date:
            sub.is_late = True
            if sub.marks is None:
                sub.status = "submitted_late"
        else:
            sub.is_late = False
            if sub.marks is None:
                sub.status = "submitted"

        sub.save()
        messages.success(
            request,
            _("Your assignment has been submitted successfully!")
            if not submission
            else _("Your assignment has been resubmitted successfully!"),
        )
    else:
        messages.error(request, _("Please provide a valid file to submit."))

    return redirect("assignment_detail", slug=assignment.slug)


@login_required
@lecturer_required
def submission_list(request, slug):
    """View all student submissions for an assignment (lecturer/admin)."""
    assignment = get_object_or_404(Assignment, slug=slug)
    course = assignment.course

    if not is_course_lecturer(request.user, course):
        messages.error(
            request, _("You are not authorized to view submissions for this assignment.")
        )
        return redirect("course_detail", slug=course.slug)

    # Fetch all enrolled students
    enrolled_records = TakenCourse.objects.filter(course=course).select_related(
        "student__student"
    ).order_by("student__student__username")

    # Fetch existing submissions
    submissions = AssignmentSubmission.objects.filter(assignment=assignment).select_related(
        "student__student", "graded_by"
    )
    submissions_by_student = {sub.student_id: sub for sub in submissions}

    roster = []
    for record in enrolled_records:
        student = record.student
        sub = submissions_by_student.get(student.id)
        roster.append({"student": student, "submission": sub})

    total_submitted = len(submissions)
    total_graded = sum(1 for s in submissions if s.marks is not None)
    context = {
        "title": f"Submissions - {assignment.title}",
        "assignment": assignment,
        "course": course,
        "roster": roster,
        "total_enrolled": len(enrolled_records),
        "total_submitted": total_submitted,
        "total_graded": total_graded,
        "pending_grading": total_submitted - total_graded,
    }
    return render(request, "assignment/submission_list.html", context)


@login_required
@lecturer_required
def submission_grade(request, pk):
    """Grade a student submission with marks and feedback (lecturer/admin)."""
    submission = get_object_or_404(
        AssignmentSubmission.objects.select_related("assignment__course", "student__student"),
        pk=pk,
    )
    assignment = submission.assignment
    course = assignment.course

    if not is_course_lecturer(request.user, course):
        messages.error(
            request, _("You are not authorized to grade this submission.")
        )
        return redirect("assignment_detail", slug=assignment.slug)

    if request.method == "POST":
        form = SubmissionGradeForm(
            request.POST, instance=submission, assignment=assignment
        )
        if form.is_valid():
            graded_sub = form.save(commit=False)
            graded_sub.graded_by = request.user
            graded_sub.graded_at = timezone.now()
            graded_sub.status = "graded"
            graded_sub.save()
            notify_assignment_graded(graded_sub)
            student_name = submission.student.student.get_full_name
            msg = (
                f"Grade saved for {student_name} "
                f"({graded_sub.marks}/{assignment.maximum_marks})."
            )
            messages.success(request, msg)
            return redirect("submission_list", slug=assignment.slug)
        messages.error(request, _("Please correct the grading errors below."))
    else:
        form = SubmissionGradeForm(instance=submission, assignment=assignment)

    context = {
        "title": f"Grade Submission - {submission.student}",
        "submission": submission,
        "assignment": assignment,
        "course": course,
        "form": form,
    }
    return render(request, "assignment/submission_grade.html", context)


@login_required
def submission_download(request, pk):
    """Securely download a student's submitted file with IDOR prevention."""
    submission = get_object_or_404(
        AssignmentSubmission.objects.select_related("assignment__course", "student__student"),
        pk=pk,
    )

    is_owner = (
        hasattr(request.user, "student")
        and submission.student.student_id == request.user.id
    )
    is_lecturer = is_course_lecturer(request.user, submission.assignment.course)

    if not (is_owner or is_lecturer or request.user.is_superuser):
        return HttpResponseForbidden(
            _("You do not have permission to download this file.")
        )

    if not submission.file or not os.path.exists(submission.file.path):
        raise Http404(_("Requested file does not exist on disk."))

    filename = os.path.basename(submission.file.name)
    file_handle = open(submission.file.path, "rb")  # pylint: disable=consider-using-with
    return FileResponse(file_handle, as_attachment=True, filename=filename)


@login_required
def user_assignments(request):
    """Overview of assignments for the logged in user (student or lecturer)."""
    if request.user.is_student:
        taken_courses = TakenCourse.objects.filter(
            student__student=request.user
        ).values_list("course_id", flat=True)
        assignments = Assignment.objects.filter(
            course_id__in=taken_courses
        ).select_related("course").order_by("-due_date")

        submissions = AssignmentSubmission.objects.filter(
            student__student=request.user
        ).select_related("assignment")
        submissions_map = {sub.assignment_id: sub for sub in submissions}

        assignment_items = []
        for a in assignments:
            assignment_items.append(
                {"assignment": a, "submission": submissions_map.get(a.id)}
            )

        context = {
            "title": _("My Assignments"),
            "assignment_items": assignment_items,
            "is_student": True,
        }
        return render(request, "assignment/user_assignments.html", context)

    if request.user.is_lecturer or request.user.is_superuser:
        if request.user.is_superuser:
            allocated_course_ids = Course.objects.values_list("id", flat=True)
        else:
            allocated_course_ids = CourseAllocation.objects.filter(
                lecturer=request.user
            ).values_list("courses", flat=True)

        assignments = Assignment.objects.filter(
            course_id__in=allocated_course_ids
        ).select_related("course").order_by("-due_date")

        assignment_items = []
        for a in assignments:
            total_sub = a.submissions.count()
            total_graded = a.submissions.filter(marks__isnull=False).count()
            assignment_items.append(
                {
                    "assignment": a,
                    "total_submissions": total_sub,
                    "total_graded": total_graded,
                    "pending_grading": total_sub - total_graded,
                }
            )

        context = {
            "title": _("Manage Assignments"),
            "assignment_items": assignment_items,
            "is_lecturer": True,
        }
        return render(request, "assignment/user_assignments.html", context)

    return redirect("home")
