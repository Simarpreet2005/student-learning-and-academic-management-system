from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from accounts.models import Student
from core.models import ActivityLog
from core.utils import unique_slug_generator
from course.models import Course

ALLOWED_ASSIGNMENT_EXTENSIONS = [
    "pdf",
    "docx",
    "doc",
    "zip",
    "rar",
    "7z",
    "txt",
    "py",
    "java",
    "cpp",
    "c",
    "sql",
    "xlsx",
    "xls",
    "pptx",
    "ppt",
]


class Assignment(models.Model):
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="assignments",
        verbose_name=_("Course"),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_assignments",
        verbose_name=_("Lecturer / Creator"),
    )
    title = models.CharField(max_length=200, verbose_name=_("Title"))
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(verbose_name=_("Instructions / Description"))
    start_date = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=_("Start / Open Date"),
        help_text=_("Optional date and time when the assignment becomes open."),
    )
    due_date = models.DateTimeField(verbose_name=_("Due Date & Time"))
    maximum_marks = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("100.00"),
        validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name=_("Maximum Marks"),
    )
    file = models.FileField(
        upload_to="assignment_attachments/%Y/%m/",
        blank=True,
        null=True,
        validators=[FileExtensionValidator(ALLOWED_ASSIGNMENT_EXTENSIONS)],
        help_text=_(
            "Optional attachment (pdf, docx, doc, zip, rar, 7z, txt, "
            "py, java, cpp, c, sql, xlsx, pptx)"
        ),
        verbose_name=_("Attachment"),
    )
    allow_resubmission = models.BooleanField(
        default=True, verbose_name=_("Allow Resubmission")
    )
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name=_("Created At")
    )
    updated_at = models.DateTimeField(
        auto_now=True, verbose_name=_("Updated At")
    )

    class Meta:
        ordering = ("-due_date", "-created_at")
        verbose_name = _("Assignment")
        verbose_name_plural = _("Assignments")

    def __str__(self):
        return f"{self.title} ({self.course.code})"

    @property
    def status(self):
        """Returns 'upcoming', 'open', or 'closed' based on current timezone."""
        now = timezone.now()
        if self.start_date and now < self.start_date:
            return "upcoming"
        if now > self.due_date:
            return "closed"
        return "open"

    @property
    def status_label(self):
        """Returns human-readable label for status."""
        s = self.status
        if s == "upcoming":
            return _("Upcoming")
        if s == "open":
            return _("Open")
        return _("Due/Closed")

    @property
    def status_badge_class(self):
        """Bootstrap badge class for status."""
        s = self.status
        if s == "upcoming":
            return "bg-info text-dark"
        if s == "open":
            return "bg-success"
        return "bg-secondary"

    @property
    def is_upcoming(self):
        return self.status == "upcoming"

    @property
    def is_open(self):
        return self.status == "open"

    @property
    def is_closed(self):
        return self.status == "closed"

    @property
    def is_past_due(self):
        return self.is_closed

    def clean(self):
        super().clean()
        if self.maximum_marks is not None and self.maximum_marks <= Decimal("0.00"):
            raise ValidationError(
                {"maximum_marks": _("Maximum marks must be greater than zero.")}
            )
        if self.start_date and self.due_date and self.start_date >= self.due_date:
            raise ValidationError(
                {"start_date": _("Start date must be before due date.")}
            )

    def get_absolute_url(self):
        return reverse("assignment_detail", kwargs={"slug": self.slug})

    def delete(self, *args, **kwargs):
        if self.file:
            self.file.delete(save=False)
        super().delete(*args, **kwargs)


@receiver(pre_save, sender=Assignment)
def assignment_pre_save_receiver(sender, instance, **kwargs):
    if not instance.slug:
        instance.slug = unique_slug_generator(instance)


@receiver(post_save, sender=Assignment)
def log_assignment_save(sender, instance, created, **kwargs):
    verb = "created" if created else "updated"
    msg = f"The assignment '{instance.title}' for course '{instance.course}' has been {verb}."
    ActivityLog.objects.create(message=_(msg))


@receiver(post_delete, sender=Assignment)
def log_assignment_delete(sender, instance, **kwargs):
    msg = f"The assignment '{instance.title}' for course '{instance.course}' has been deleted."
    ActivityLog.objects.create(message=_(msg))


class AssignmentSubmission(models.Model):
    SUBMISSION_STATUS = (
        ("submitted", _("Submitted")),
        ("submitted_late", _("Submitted Late")),
        ("graded", _("Graded")),
    )

    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name="submissions",
        verbose_name=_("Assignment"),
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="assignment_submissions",
        verbose_name=_("Student"),
    )
    file = models.FileField(
        upload_to="assignment_submissions/%Y/%m/",
        validators=[FileExtensionValidator(ALLOWED_ASSIGNMENT_EXTENSIONS)],
        help_text=_(
            "Submission file (pdf, docx, doc, zip, rar, 7z, txt, py, java, cpp, c, sql, xlsx, pptx)"
        ),
        verbose_name=_("Submitted File"),
    )
    comment = models.TextField(
        blank=True, null=True, verbose_name=_("Student Comments / Notes")
    )
    submitted_at = models.DateTimeField(
        auto_now=True, verbose_name=_("Submission Date")
    )
    is_late = models.BooleanField(default=False, verbose_name=_("Is Late Submission"))
    status = models.CharField(
        max_length=20,
        choices=SUBMISSION_STATUS,
        default="submitted",
        verbose_name=_("Status"),
    )

    # Grading attributes
    marks = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name=_("Marks / Score"),
    )
    feedback = models.TextField(
        blank=True, null=True, verbose_name=_("Lecturer Feedback")
    )
    graded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="graded_submissions",
        verbose_name=_("Graded By"),
    )
    graded_at = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Graded At")
    )

    class Meta:
        unique_together = ("assignment", "student")
        ordering = ("-submitted_at",)
        verbose_name = _("Assignment Submission")
        verbose_name_plural = _("Assignment Submissions")

    def __str__(self):
        student_id = getattr(self.student.student, "username", str(self.student))
        return f"{student_id} - {self.assignment.title}"

    @property
    def status_label(self):
        """Returns human-readable label for submission status."""
        if self.status == "graded":
            return _("Graded")
        if self.status == "submitted_late":
            return _("Submitted Late")
        if self.status == "submitted":
            return _("Submitted")
        return _("Not Submitted")

    @property
    def status_badge_class(self):
        """Bootstrap badge class for submission status."""
        if self.status == "graded":
            return "bg-success"
        if self.status == "submitted_late":
            return "bg-warning text-dark"
        if self.status == "submitted":
            return "bg-primary"
        return "bg-secondary"

    def clean(self):
        super().clean()
        if self.marks is not None and hasattr(self, "assignment") and self.assignment:
            if self.marks < Decimal("0.00"):
                raise ValidationError(
                    {"marks": _("Marks cannot be negative.")}
                )
            if self.marks > self.assignment.maximum_marks:
                err_msg = (
                    f"Marks ({self.marks}) cannot exceed maximum marks "
                    f"({self.assignment.maximum_marks})."
                )
                raise ValidationError({"marks": _(err_msg)})

    def save(self, *args, **kwargs):
        # Auto-compute late submission
        if self.assignment and self.assignment.due_date:
            current_time = timezone.now()
            if current_time > self.assignment.due_date:
                self.is_late = True

        # Auto-update status
        if self.marks is not None:
            self.status = "graded"
            if not self.graded_at:
                self.graded_at = timezone.now()
        elif self.is_late:
            self.status = "submitted_late"
        else:
            self.status = "submitted"

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.file:
            self.file.delete(save=False)
        super().delete(*args, **kwargs)
