"""Core foundation models: Abstract base timestamps and Institutional Academic Events."""
from django.core.exceptions import ValidationError
from django.db import models


class TimestampedModel(models.Model):
    """Abstract base model providing self-updating creation and modification timestamps."""

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Updated At")

    class Meta:
        abstract = True


class EventType(models.TextChoices):
    """Institutional calendar event classifications."""

    ACADEMIC = "ACADEMIC", "Academic Milestone"
    EXAMINATION = "EXAMINATION", "Examination Period"
    REGISTRATION = "REGISTRATION", "Course Registration Window"
    HOLIDAY = "HOLIDAY", "Institutional Holiday"
    CEREMONY = "CEREMONY", "Convocation / Ceremony"
    LECTURE_RECESS = "LECTURE_RECESS", "Lecture Recess / Break"
    OTHER = "OTHER", "General Campus Event"


class AcademicEvent(TimestampedModel):
    """Official master institutional calendar event."""

    title = models.CharField(max_length=200, verbose_name="Event Title")
    event_type = models.CharField(
        max_length=30,
        choices=EventType.choices,
        default=EventType.ACADEMIC,
        verbose_name="Event Type",
    )
    start_date = models.DateTimeField(verbose_name="Start Date & Time")
    end_date = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="End Date & Time",
        help_text="Optional end timestamp for multi-day events.",
    )
    description = models.TextField(blank=True, verbose_name="Description")
    location = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Location / Venue",
        help_text="Optional physical hall, campus lawn, or virtual venue identifier.",
    )
    is_published = models.BooleanField(
        default=True,
        verbose_name="Published Status",
        help_text="Unpublished events remain visible only to administrators.",
    )

    class Meta:
        ordering = ["start_date"]
        verbose_name = "Academic Event"
        verbose_name_plural = "Academic Events"

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError({"end_date": "End date and time cannot be earlier than start date and time."})

    def __str__(self) -> str:
        return f"{self.title} ({self.get_event_type_display()})"
