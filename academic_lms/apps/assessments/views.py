"""Role-scoped assignment authoring, submission, and grading views."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.academics.models import CourseAllocation, EnrollmentStatus, StudentEnrollment
from .forms import AssignmentForm, AssignmentGradeForm, AssignmentSubmissionForm
from .models import Assignment, AssignmentSubmission


def _can_manage_assignment(user, assignment):
    return user.is_admin_role or (
        user.is_lecturer_role
        and CourseAllocation.objects.filter(
            course=assignment.course, lecturer=user, is_active=True
        ).exists()
    )


@login_required
def assignment_list_view(request):
    """Show assignments available to the current student or courses managed by staff."""
    assignments = Assignment.objects.filter(is_active=True).select_related("course", "created_by")
    if request.user.is_student_role:
        enrolled_ids = StudentEnrollment.objects.filter(
            student=request.user, status=EnrollmentStatus.ENROLLED, is_active=True
        ).values_list("course_id", flat=True)
        assignments = assignments.filter(course_id__in=enrolled_ids, is_published=True)
    elif request.user.is_lecturer_role:
        course_ids = CourseAllocation.objects.filter(
            lecturer=request.user, is_active=True
        ).values_list("course_id", flat=True)
        assignments = assignments.filter(course_id__in=course_ids)
    elif not request.user.is_admin_role:
        raise PermissionDenied
    submissions = {
        item.assignment_id: item
        for item in AssignmentSubmission.objects.filter(student=request.user, is_active=True)
    }
    rows = [(assignment, submissions.get(assignment.pk)) for assignment in assignments.order_by("due_date")]
    return render(request, "assessments/assignment_list.html", {
        "assignment_rows": rows,
        "can_create": request.user.is_admin_role or request.user.is_lecturer_role,
    })


@login_required
def assignment_create_view(request):
    if not (request.user.is_admin_role or request.user.is_lecturer_role):
        raise PermissionDenied
    form = AssignmentForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        assignment = form.save(commit=False)
        assignment.created_by = request.user
        assignment.save()
        messages.success(request, "Assignment created.")
        return redirect("assessments:detail", pk=assignment.pk)
    return render(request, "assessments/assignment_form.html", {"form": form, "heading": "Create assignment"})


@login_required
def assignment_edit_view(request, pk):
    assignment = get_object_or_404(Assignment, pk=pk, is_active=True)
    if not _can_manage_assignment(request.user, assignment):
        raise PermissionDenied
    form = AssignmentForm(request.POST or None, instance=assignment, user=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Assignment updated.")
        return redirect("assessments:detail", pk=assignment.pk)
    return render(request, "assessments/assignment_form.html", {"form": form, "heading": "Edit assignment"})


@login_required
def assignment_detail_view(request, pk):
    assignment = get_object_or_404(
        Assignment.objects.select_related("course", "created_by"), pk=pk, is_active=True
    )
    manager = _can_manage_assignment(request.user, assignment)
    enrolled = request.user.is_student_role and StudentEnrollment.objects.filter(
        student=request.user, course=assignment.course,
        status=EnrollmentStatus.ENROLLED, is_active=True,
    ).exists()
    if not manager and not (enrolled and assignment.is_published):
        raise PermissionDenied
    submission = None
    form = None
    if request.user.is_student_role:
        submission = AssignmentSubmission.objects.filter(
            assignment=assignment, student=request.user, is_active=True
        ).first()
        form = AssignmentSubmissionForm(instance=submission)
        cutoff = assignment.cutoff_date or assignment.due_date
        if request.method == "POST":
            if timezone.now() > cutoff:
                messages.error(request, "The submission cutoff has passed.")
            else:
                form = AssignmentSubmissionForm(request.POST, request.FILES, instance=submission)
                if form.is_valid():
                    submission = form.save(commit=False)
                    submission.assignment = assignment
                    submission.student = request.user
                    submission.submitted_at = timezone.now()
                    submission.status = (
                        AssignmentSubmission.SubmissionStatus.LATE
                        if submission.submitted_at > assignment.due_date
                        else AssignmentSubmission.SubmissionStatus.SUBMITTED
                    )
                    submission.score = None
                    submission.lecturer_feedback = ""
                    submission.save()
                    messages.success(request, "Your assignment submission was saved.")
                    return redirect("assessments:detail", pk=assignment.pk)
    submissions = None
    if manager:
        submissions = assignment.submissions.filter(is_active=True).select_related("student").order_by("student__last_name", "student__first_name")
    return render(request, "assessments/assignment_detail.html", {
        "assignment": assignment, "submission": submission, "form": form,
        "submissions": submissions, "can_manage": manager,
        "can_submit": request.user.is_student_role and timezone.now() <= (assignment.cutoff_date or assignment.due_date),
    })


@login_required
def assignment_grade_view(request, submission_id):
    submission = get_object_or_404(
        AssignmentSubmission.objects.select_related("assignment", "assignment__course"),
        pk=submission_id, is_active=True,
    )
    if not _can_manage_assignment(request.user, submission.assignment):
        raise PermissionDenied
    form = AssignmentGradeForm(request.POST or None, instance=submission)
    if request.method == "POST" and form.is_valid():
        graded = form.save(commit=False)
        graded.status = AssignmentSubmission.SubmissionStatus.GRADED
        graded.save()
        messages.success(request, "Submission graded.")
        return redirect("assessments:detail", pk=submission.assignment_id)
    return render(request, "assessments/assignment_grade.html", {"form": form, "submission": submission})


@login_required
def assignment_submission_download_view(request, submission_id):
    submission = get_object_or_404(
        AssignmentSubmission.objects.select_related("assignment", "assignment__course"),
        pk=submission_id, is_active=True,
    )
    is_owner = request.user.is_student_role and submission.student_id == request.user.pk
    if not is_owner and not _can_manage_assignment(request.user, submission.assignment):
        raise PermissionDenied
    if not submission.submission_file:
        from django.http import Http404
        raise Http404("No file was attached to this submission.")
    return FileResponse(
        submission.submission_file.open("rb"),
        as_attachment=True,
        filename=submission.submission_file.name.rsplit("/", 1)[-1],
    )
