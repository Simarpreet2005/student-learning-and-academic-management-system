"""Quizzes, Questions, Attempts, and Answers Data Models."""
from datetime import timedelta
from decimal import Decimal
import random

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from apps.academics.models import Course


class QuizStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft (Under Construction)"
    PUBLISHED = "PUBLISHED", "Published (Active for Students)"
    ARCHIVED = "ARCHIVED", "Archived (Concluded)"


class QuestionType(models.TextChoices):
    MULTIPLE_CHOICE = "MULTIPLE_CHOICE", "Multiple Choice (Single Answer)"
    TRUE_FALSE = "TRUE_FALSE", "True / False"
    SHORT_ANSWER = "SHORT_ANSWER", "Short Answer (Manual Grading)"


class AttemptStatus(models.TextChoices):
    IN_PROGRESS = "IN_PROGRESS", "In Progress"
    SUBMITTED = "SUBMITTED", "Submitted (Pending Manual Grading)"
    COMPLETED = "COMPLETED", "Completed & Graded"
    EXPIRED = "EXPIRED", "Expired / Auto-Submitted"


class Quiz(models.Model):
    """Timed quiz or interactive assessment linked to a course curriculum offering."""

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="quizzes",
        verbose_name="Course",
    )
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_quizzes",
        limit_choices_to={"role": "LECTURER"},
        verbose_name="Course Lecturer / Creator",
    )
    title = models.CharField(max_length=200, verbose_name="Quiz Title")
    instructions = models.TextField(
        blank=True,
        verbose_name="Instructions & Guidelines",
        help_text="Provide exam instructions, academic honesty guidelines, and permitted materials.",
    )
    available_from = models.DateTimeField(
        verbose_name="Available From",
        help_text="Start of the availability window during which students may begin an attempt.",
    )
    available_to = models.DateTimeField(
        verbose_name="Available Until",
        help_text="End of the availability window after which no new attempts may start.",
    )
    duration_minutes = models.PositiveIntegerField(
        default=30,
        verbose_name="Duration (Minutes)",
        help_text="Server-enforced time limit once an attempt begins.",
        validators=[MinValueValidator(1), MaxValueValidator(360)],
    )
    estimated_effort_hours = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.1"))],
        verbose_name="Estimated Effort (Hours)",
        help_text="Optional estimated prep effort in hours entered by lecturer. Leave blank if not estimated.",
    )
    total_marks = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Total Marks",
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Total maximum marks across all questions.",
    )
    pass_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("50.00"),
        verbose_name="Pass Percentage (%)",
        validators=[MinValueValidator(Decimal("0.00")), MaxValueValidator(Decimal("100.00"))],
        help_text="Minimum score percentage required to earn a passing grade.",
    )
    max_attempts = models.PositiveIntegerField(
        default=1,
        verbose_name="Maximum Attempts Allowed",
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        help_text="Maximum number of attempts each enrolled student is permitted.",
    )
    status = models.CharField(
        max_length=20,
        choices=QuizStatus.choices,
        default=QuizStatus.DRAFT,
        verbose_name="Publication Status",
    )
    shuffle_questions = models.BooleanField(
        default=False,
        verbose_name="Shuffle Question Order",
        help_text="Reliably randomizes question presentation order per attempt without affecting answer integrity.",
    )
    shuffle_options = models.BooleanField(
        default=False,
        verbose_name="Shuffle Option Order",
        help_text="Reliably randomizes option order per question per attempt.",
    )
    release_correct_answers = models.BooleanField(
        default=False,
        verbose_name="Release Answer Key",
        help_text="Permits students and parents to inspect correct options and model answers once grading is complete.",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Active (Soft Delete)",
        help_text="Soft deactivation toggle preserving historical grade integrity.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Quiz"
        verbose_name_plural = "Quizzes"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.course.code} — {self.title} ({self.get_status_display()})"

    @property
    def is_published(self) -> bool:
        return self.status == QuizStatus.PUBLISHED

    def is_available_now(self) -> bool:
        """Evaluate if the quiz is currently open for new student attempts."""
        now = timezone.now()
        if not self.is_active or self.status != QuizStatus.PUBLISHED:
            return False
        return self.available_from <= now <= self.available_to

    def is_upcoming(self) -> bool:
        return self.is_active and timezone.now() < self.available_from

    def is_expired(self) -> bool:
        return timezone.now() > self.available_to

    def question_count(self) -> int:
        return self.questions.count()

    def computed_total_marks(self) -> Decimal:
        """Calculate the sum of marks from all constituent questions."""
        total = self.questions.aggregate(models.Sum("marks"))["marks__sum"]
        return total if total is not None else Decimal("0.00")

    def sync_total_marks(self) -> Decimal:
        """Synchronize the quiz total_marks field with the exact sum of questions."""
        computed = self.computed_total_marks()
        if self.total_marks != computed:
            self.total_marks = computed
            self.save(update_fields=["total_marks", "updated_at"])
        return computed

    def has_short_answer_questions(self) -> bool:
        """Check if this quiz contains questions requiring manual lecturer grading."""
        return self.questions.filter(question_type=QuestionType.SHORT_ANSWER).exists()

    def clean(self):
        super().clean()
        if self.available_from and self.available_to:
            if self.available_from >= self.available_to:
                raise ValidationError(
                    {"available_to": "The availability closing date/time must be strictly after the start date/time."}
                )

        if self.status == QuizStatus.PUBLISHED and self.pk:
            q_count = self.questions.count()
            if q_count == 0:
                raise ValidationError(
                    {"status": "Cannot publish a quiz with no questions. Add at least one question first."}
                )

            # Validate each question's option consistency
            for q in self.questions.all():
                q.validate_options()


class Question(models.Model):
    """An assessment question belonging to a specific Quiz."""

    quiz = models.ForeignKey(
        Quiz,
        on_delete=models.CASCADE,
        related_name="questions",
        verbose_name="Quiz",
    )
    text = models.TextField(verbose_name="Question Prompt")
    question_type = models.CharField(
        max_length=20,
        choices=QuestionType.choices,
        default=QuestionType.MULTIPLE_CHOICE,
        verbose_name="Question Type",
    )
    marks = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("1.00"),
        validators=[MinValueValidator(Decimal("0.10"))],
        verbose_name="Marks",
        help_text="Marks allocated for a fully correct answer.",
    )
    order = models.PositiveIntegerField(default=1, verbose_name="Sort Order")
    model_answer = models.TextField(
        blank=True,
        verbose_name="Model Answer / Grading Rubric",
        help_text="Expected answer, key criteria, or rubric points used by the lecturer for manual evaluation.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Quiz Question"
        verbose_name_plural = "Quiz Questions"
        ordering = ["order", "id"]

    def __str__(self) -> str:
        prompt_snippet = (self.text[:60] + "...") if len(self.text) > 60 else self.text
        return f"Q{self.order} ({self.get_question_type_display()}): {prompt_snippet}"

    def validate_options(self):
        """Ensure options are structurally valid for this question type."""
        if self.question_type == QuestionType.MULTIPLE_CHOICE:
            opt_count = self.options.count()
            if opt_count < 2:
                raise ValidationError(
                    f"Question '{self.text[:30]}' must have at least 2 options (currently has {opt_count})."
                )
            correct_count = self.options.filter(is_correct=True).count()
            if correct_count != 1:
                raise ValidationError(
                    f"Question '{self.text[:30]}' must have exactly 1 correct option (currently has {correct_count})."
                )
        elif self.question_type == QuestionType.TRUE_FALSE:
            opt_count = self.options.count()
            if opt_count != 2:
                raise ValidationError(
                    f"True/False question '{self.text[:30]}' must have exactly 2 options (True and False)."
                )
            correct_count = self.options.filter(is_correct=True).count()
            if correct_count != 1:
                raise ValidationError(
                    f"True/False question '{self.text[:30]}' must have exactly 1 correct option."
                )


class QuestionOption(models.Model):
    """Selectable choice option for Multiple-Choice and True/False questions."""

    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="options",
        verbose_name="Question",
    )
    text = models.CharField(max_length=500, verbose_name="Option Text")
    is_correct = models.BooleanField(
        default=False,
        verbose_name="Is Correct Option",
        help_text="Designates this option as the correct answer.",
    )
    order = models.PositiveIntegerField(default=1, verbose_name="Sort Order")

    class Meta:
        verbose_name = "Question Option"
        verbose_name_plural = "Question Options"
        ordering = ["order", "id"]

    def __str__(self) -> str:
        marker = " [CORRECT]" if self.is_correct else ""
        return f"{self.text}{marker}"


class QuizAttempt(models.Model):
    """A distinct student sitting/attempt of a published quiz."""

    quiz = models.ForeignKey(
        Quiz,
        on_delete=models.CASCADE,
        related_name="attempts",
        verbose_name="Quiz",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="quiz_attempts",
        limit_choices_to={"role": "STUDENT"},
        verbose_name="Student",
    )
    attempt_number = models.PositiveIntegerField(default=1, verbose_name="Attempt Number")
    status = models.CharField(
        max_length=20,
        choices=AttemptStatus.choices,
        default=AttemptStatus.IN_PROGRESS,
        verbose_name="Status",
    )
    started_at = models.DateTimeField(default=timezone.now, verbose_name="Started At")
    submitted_at = models.DateTimeField(null=True, blank=True, verbose_name="Submitted At")
    graded_at = models.DateTimeField(null=True, blank=True, verbose_name="Graded At")
    graded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="graded_quiz_attempts",
        verbose_name="Grading Lecturer",
    )
    score_obtained = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Score Obtained",
    )
    total_marks = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Total Possible Marks",
    )
    percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Score Percentage (%)",
    )
    is_passed = models.BooleanField(default=False, verbose_name="Passed Status")
    feedback = models.TextField(blank=True, verbose_name="Lecturer Overall Feedback")
    question_order = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Assigned Question Order",
        help_text="Immutable list of question IDs preserving randomized sequence.",
    )
    option_order = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Assigned Option Order per Question",
        help_text="Immutable mapping of question IDs to randomized option ID sequences.",
    )

    class Meta:
        verbose_name = "Quiz Attempt"
        verbose_name_plural = "Quiz Attempts"
        constraints = [
            models.UniqueConstraint(
                fields=["quiz", "student", "attempt_number"],
                name="unique_quiz_student_attempt_number",
            )
        ]
        ordering = ["-started_at"]

    def __str__(self) -> str:
        return f"{self.student.get_full_name} — {self.quiz.title} (Attempt #{self.attempt_number}: {self.get_status_display()})"

    @property
    def effective_deadline(self):
        """Server-enforced cutoff timestamp for this specific attempt."""
        duration_deadline = self.started_at + timedelta(minutes=self.quiz.duration_minutes)
        if self.quiz.available_to:
            return min(duration_deadline, self.quiz.available_to)
        return duration_deadline

    def get_remaining_seconds(self) -> int:
        """Calculate remaining time in seconds based on server clock."""
        now = timezone.now()
        remaining = (self.effective_deadline - now).total_seconds()
        return max(0, int(remaining))

    def is_time_expired(self, grace_period_seconds: int = 45) -> bool:
        """Check if attempt exceeded allowed duration plus network grace period."""
        now = timezone.now()
        return now > (self.effective_deadline + timedelta(seconds=grace_period_seconds))

    def is_modifiable(self) -> bool:
        """Answers may only be saved or submitted while in-progress and within time."""
        return self.status == AttemptStatus.IN_PROGRESS and not self.is_time_expired()

    def has_pending_manual_grading(self) -> bool:
        """Check if any short-answer question in this attempt remains unreviewed."""
        return self.answers.filter(
            question__question_type=QuestionType.SHORT_ANSWER,
            graded_at__isnull=True,
        ).exists()

    def initialize_question_ordering(self):
        """Generate and freeze randomized or ordered questions and options for this attempt."""
        questions_qs = self.quiz.questions.all().order_by("order", "id")
        q_ids = list(questions_qs.values_list("id", flat=True))

        if self.quiz.shuffle_questions:
            random.shuffle(q_ids)
        self.question_order = q_ids

        opt_order = {}
        for q in questions_qs:
            opts = list(q.options.all().order_by("order", "id").values_list("id", flat=True))
            if self.quiz.shuffle_options:
                random.shuffle(opts)
            opt_order[str(q.id)] = opts
        self.option_order = opt_order


class StudentAnswer(models.Model):
    """A student's recorded answer to an individual quiz question."""

    attempt = models.ForeignKey(
        QuizAttempt,
        on_delete=models.CASCADE,
        related_name="answers",
        verbose_name="Quiz Attempt",
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="student_answers",
        verbose_name="Question",
    )
    selected_option = models.ForeignKey(
        QuestionOption,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Selected Option",
    )
    text_response = models.TextField(blank=True, verbose_name="Short Answer Response")
    marks_awarded = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Marks Awarded",
    )
    is_correct = models.BooleanField(
        null=True,
        blank=True,
        verbose_name="Is Correct",
        help_text="Evaluated automatically for objective questions or manually for subjective questions.",
    )
    graded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Graded By",
    )
    graded_at = models.DateTimeField(null=True, blank=True, verbose_name="Graded At")
    lecturer_comment = models.TextField(
        blank=True,
        verbose_name="Feedback / Rubric Note",
        help_text="Lecturer commentary, rubric rationale, or constructive evaluation notes.",
    )

    class Meta:
        verbose_name = "Student Answer"
        verbose_name_plural = "Student Answers"
        constraints = [
            models.UniqueConstraint(
                fields=["attempt", "question"],
                name="unique_attempt_question_answer",
            )
        ]

    def __str__(self) -> str:
        return f"Attempt #{self.attempt.attempt_number} — Q{self.question.order}: {self.marks_awarded}/{self.question.marks} marks"
