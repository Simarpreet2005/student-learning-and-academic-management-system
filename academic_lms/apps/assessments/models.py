"""Assessments application models: Assignments, Submissions, and Quizzes Facade.

Provides course-linked Assignment deliverables and student AssignmentSubmissions,
while re-exporting Quiz models from apps.quizzes to maintain a unified assessment interface.
"""
from decimal import Decimal
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from apps.courseware.validators import resource_upload_path, validate_resource_file

from apps.quizzes.models import (  # noqa: F401
    Quiz,
    QuizStatus,
    Question,
    QuestionType,
    QuestionOption,
    QuizAttempt,
    AttemptStatus,
    StudentAnswer,
)

__all__ = (
    "Quiz",
    "QuizStatus",
    "Question",
    "QuestionType",
    "QuestionOption",
    "QuizAttempt",
    "AttemptStatus",
    "StudentAnswer",
    "Assignment",
    "AssignmentSubmission",
)


class Assignment(models.Model):
    """Course-linked academic assignment deliverable."""

    course = models.ForeignKey(
        "academics.Course",
        on_delete=models.CASCADE,
        related_name="assignments",
        verbose_name="Course",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_assignments",
        verbose_name="Lecturer / Creator",
    )
    title = models.CharField(max_length=200, verbose_name="Title")
    description = models.TextField(blank=True, verbose_name="Instructions / Description")
    due_date = models.DateTimeField(verbose_name="Due Date & Time")
    cutoff_date = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Hard Cutoff Date",
        help_text="Optional hard cutoff date past which submissions are rejected.",
    )
    maximum_marks = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("100.00"),
        validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name="Maximum Marks",
    )
    estimated_effort_hours = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.1"))],
        verbose_name="Estimated Effort (Hours)",
        help_text="Optional estimated effort in hours entered by lecturer. Leave blank if not estimated.",
    )
    is_published = models.BooleanField(default=True, verbose_name="Published")
    is_active = models.BooleanField(default=True, verbose_name="Active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["due_date", "created_at"]
        verbose_name = "Assignment"
        verbose_name_plural = "Assignments"

    def __str__(self) -> str:
        return f"{self.title} ({self.course.code})"

    @property
    def has_estimated_effort(self) -> bool:
        return self.estimated_effort_hours is not None


class AssignmentSubmission(models.Model):
    """Student submission record for an assignment."""

    class SubmissionStatus(models.TextChoices):
        SUBMITTED = "SUBMITTED", "Submitted"
        GRADED = "GRADED", "Graded"
        LATE = "LATE", "Late"

    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name="submissions",
        verbose_name="Assignment",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="assignment_submissions",
        limit_choices_to={"role": "STUDENT"},
        verbose_name="Student",
    )
    submitted_at = models.DateTimeField(default=timezone.now, verbose_name="Submitted At")
    status = models.CharField(
        max_length=20,
        choices=SubmissionStatus.choices,
        default=SubmissionStatus.SUBMITTED,
        verbose_name="Status",
    )
    submission_notes = models.TextField(blank=True, verbose_name="Submission Notes")
    submission_file = models.FileField(
        upload_to=resource_upload_path,
        validators=[validate_resource_file],
        blank=True,
        verbose_name="Submitted File",
    )
    score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Score Awarded",
    )
    lecturer_feedback = models.TextField(blank=True, verbose_name="Lecturer Feedback")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["assignment", "student"],
                name="unique_assignment_student_submission",
            )
        ]
        ordering = ["-submitted_at"]
        verbose_name = "Assignment Submission"
        verbose_name_plural = "Assignment Submissions"

    def __str__(self) -> str:
        return f"{self.assignment.title} - {self.student.get_full_name}"

    def clean(self):
        super().clean()
        if self.score is not None and self.assignment_id:
            if self.score < 0 or self.score > self.assignment.maximum_marks:
                from django.core.exceptions import ValidationError
                raise ValidationError({"score": "Score must be between zero and the assignment's maximum marks."})
