"""Models for Courseware and Digital Learning Materials."""
import os
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from .validators import (
    resource_upload_path,
    validate_resource_file,
    validate_resource_url,
)


class CourseModule(models.Model):
    """Curriculum unit or topic grouping within a Course (e.g. Week 1: Introduction)."""

    course = models.ForeignKey(
        "academics.Course",
        on_delete=models.CASCADE,
        related_name="modules",
        verbose_name="Associated Course",
    )
    title = models.CharField(max_length=200, verbose_name="Module / Topic Title")
    description = models.TextField(blank=True, verbose_name="Module Description")
    order = models.PositiveIntegerField(default=1, verbose_name="Order / Sequence")
    is_active = models.BooleanField(
        default=True,
        verbose_name="Active Status",
        help_text="Soft deactivation toggle",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Course Module"
        verbose_name_plural = "Course Modules"
        ordering = ["course", "order", "id"]

    def __str__(self) -> str:
        return f"{self.course.code}: {self.title}"


class ResourceType(models.TextChoices):
    DOCUMENT = "DOCUMENT", "Document (PDF, Word, Text)"
    PRESENTATION = "PRESENTATION", "Presentation (PowerPoint, Slides)"
    EXTERNAL_LINK = "EXTERNAL_LINK", "External Link (Web Reference)"
    VIDEO_LINK = "VIDEO_LINK", "Video Link (External Video URL)"


class ResourceStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    PUBLISHED = "PUBLISHED", "Published"
    ARCHIVED = "ARCHIVED", "Archived"


class LearningResource(models.Model):
    """Digital educational material attached to a Course."""

    course = models.ForeignKey(
        "academics.Course",
        on_delete=models.CASCADE,
        related_name="resources",
        verbose_name="Course",
    )
    module = models.ForeignKey(
        CourseModule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resources",
        verbose_name="Topic / Module",
    )
    title = models.CharField(max_length=200, verbose_name="Resource Title")
    description = models.TextField(blank=True, verbose_name="Description / Overview")
    resource_type = models.CharField(
        max_length=20,
        choices=ResourceType.choices,
        default=ResourceType.DOCUMENT,
        verbose_name="Resource Type",
    )
    status = models.CharField(
        max_length=20,
        choices=ResourceStatus.choices,
        default=ResourceStatus.PUBLISHED,
        verbose_name="Publication Status",
    )
    file = models.FileField(
        upload_to=resource_upload_path,
        blank=True,
        null=True,
        validators=[validate_resource_file],
        verbose_name="Resource File",
    )
    original_filename = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Original Filename",
    )
    file_size = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="File Size (Bytes)",
    )
    external_url = models.URLField(
        max_length=500,
        blank=True,
        validators=[validate_resource_url],
        verbose_name="External Resource URL",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_resources",
        verbose_name="Creator / Uploader",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Active Status",
        help_text="Soft deactivation toggle",
    )
    published_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Publication Date",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Last Updated")

    class Meta:
        verbose_name = "Learning Resource"
        verbose_name_plural = "Learning Resources"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["course", "status", "is_active"]),
            models.Index(fields=["resource_type"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self) -> str:
        return f"[{self.course.code}] {self.title} ({self.get_resource_type_display()})"

    @property
    def is_published(self) -> bool:
        return self.status == ResourceStatus.PUBLISHED and self.is_active

    @property
    def has_file(self) -> bool:
        return bool(self.file)

    @property
    def file_extension(self) -> str:
        if self.original_filename:
            return os.path.splitext(self.original_filename)[1].lower()
        if self.file:
            return os.path.splitext(self.file.name)[1].lower()
        return ""

    @property
    def file_size_display(self) -> str:
        if not self.file_size:
            return ""
        size = self.file_size
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size / (1024 * 1024):.2f} MB"

    def clean(self):
        super().clean()

        # Enforce resource type constraints
        if self.resource_type in [ResourceType.EXTERNAL_LINK, ResourceType.VIDEO_LINK]:
            if not self.external_url:
                raise ValidationError({"external_url": "An external URL is required for link resources."})
            validate_resource_url(self.external_url)

        if self.resource_type in [ResourceType.DOCUMENT, ResourceType.PRESENTATION]:
            if not self.file and not self.external_url:
                raise ValidationError("Either a file upload or an external URL is required for this resource type.")

        if self.file:
            validate_resource_file(self.file)

        if self.external_url:
            validate_resource_url(self.external_url)

        # Ensure module belongs to the same course if specified
        if self.module and self.course_id and self.module.course_id != self.course_id:
            raise ValidationError({"module": "The selected module does not belong to the selected course."})

    def save(self, *args, **kwargs):
        # Auto-capture original filename and size if file is newly uploaded
        if self.file:
            if not self.original_filename:
                self.original_filename = os.path.basename(getattr(self.file, "name", ""))
            if hasattr(self.file, "size") and not self.file_size:
                self.file_size = self.file.size

        # Set publication date on initial publish
        if self.status == ResourceStatus.PUBLISHED and not self.published_at:
            self.published_at = timezone.now()

        super().save(*args, **kwargs)
