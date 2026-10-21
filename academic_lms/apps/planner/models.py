"""Models for Rule-Based Smart Academic Workload Planner.

Provides:
- StudentStudyBudget: Student-configured weekly study availability by weekday.
- TaskEffortProfile: Reference effort standards by task category.

All planning calculations are 100% deterministic with zero external AI/LLM dependencies.
"""
from decimal import Decimal
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class StudentStudyBudget(models.Model):
    """Student-configured weekly available study hours by weekday.

    Allows learners to define their weekly study availability (in hours per day).
    The WorkloadPlannerService uses this to compute the Workload Pressure Index (WPI),
    detect over-capacity conditions, and build a deterministic 7-day study schedule.
    """

    student = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="study_budget",
        limit_choices_to={"role": "STUDENT"},
        verbose_name="Student",
    )
    monday_hours = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        default=Decimal("2.0"),
        validators=[MinValueValidator(Decimal("0.0")), MaxValueValidator(Decimal("24.0"))],
        verbose_name="Monday Study Hours",
    )
    tuesday_hours = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        default=Decimal("2.0"),
        validators=[MinValueValidator(Decimal("0.0")), MaxValueValidator(Decimal("24.0"))],
        verbose_name="Tuesday Study Hours",
    )
    wednesday_hours = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        default=Decimal("2.0"),
        validators=[MinValueValidator(Decimal("0.0")), MaxValueValidator(Decimal("24.0"))],
        verbose_name="Wednesday Study Hours",
    )
    thursday_hours = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        default=Decimal("2.0"),
        validators=[MinValueValidator(Decimal("0.0")), MaxValueValidator(Decimal("24.0"))],
        verbose_name="Thursday Study Hours",
    )
    friday_hours = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        default=Decimal("2.0"),
        validators=[MinValueValidator(Decimal("0.0")), MaxValueValidator(Decimal("24.0"))],
        verbose_name="Friday Study Hours",
    )
    saturday_hours = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        default=Decimal("4.0"),
        validators=[MinValueValidator(Decimal("0.0")), MaxValueValidator(Decimal("24.0"))],
        verbose_name="Saturday Study Hours",
    )
    sunday_hours = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        default=Decimal("4.0"),
        validators=[MinValueValidator(Decimal("0.0")), MaxValueValidator(Decimal("24.0"))],
        verbose_name="Sunday Study Hours",
    )
    notes = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Personal Study Notes",
        help_text="Optional personal constraints or preferences (e.g. 'Concentrate on weekends').",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Student Study Budget"
        verbose_name_plural = "Student Study Budgets"

    def __str__(self) -> str:
        return f"{self.student.get_full_name} ({self.target_weekly_hours}h/week)"

    @property
    def target_weekly_hours(self) -> Decimal:
        """Total available study hours across the entire 7-day week."""
        return (
            self.monday_hours
            + self.tuesday_hours
            + self.wednesday_hours
            + self.thursday_hours
            + self.friday_hours
            + self.saturday_hours
            + self.sunday_hours
        )

    def get_hours_for_weekday(self, weekday_int: int) -> Decimal:
        """Return allocated hours for a Python weekday integer (0 = Monday, ..., 6 = Sunday)."""
        mapping = {
            0: self.monday_hours,
            1: self.tuesday_hours,
            2: self.wednesday_hours,
            3: self.thursday_hours,
            4: self.friday_hours,
            5: self.saturday_hours,
            6: self.sunday_hours,
        }
        return mapping.get(weekday_int, Decimal("0.0"))


class TaskEffortProfile(models.Model):
    """Institutional reference complexity guidelines by deliverable category."""

    class TaskType(models.TextChoices):
        ASSIGNMENT = "ASSIGNMENT", "Course Assignment"
        QUIZ = "QUIZ", "Quiz Preparation"
        PROJECT = "PROJECT", "Major Term Project"
        READING = "READING", "Required Reading / Syllabus Review"

    task_type = models.CharField(
        max_length=30,
        choices=TaskType.choices,
        unique=True,
        verbose_name="Task Type",
    )
    default_effort_hours = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        default=Decimal("3.0"),
        validators=[MinValueValidator(Decimal("0.5")), MaxValueValidator(Decimal("40.0"))],
        verbose_name="Reference Effort (Hours)",
        help_text="Institutional baseline reference for guidelines only.",
    )
    description = models.TextField(blank=True, verbose_name="Description")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Task Effort Reference Profile"
        verbose_name_plural = "Task Effort Reference Profiles"

    def __str__(self) -> str:
        return f"{self.get_task_type_display()} ({self.default_effort_hours}h reference)"
