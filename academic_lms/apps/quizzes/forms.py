"""Forms for Quiz creation, Question authoring, and Lecturer Grading Desk."""
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory

from apps.academics.models import Course, CourseAllocation
from .models import (
    Question,
    QuestionOption,
    QuestionType,
    Quiz,
    QuizAttempt,
    QuizStatus,
    StudentAnswer,
)


class QuizForm(forms.ModelForm):
    """Form for lecturers to create and update Quizzes."""

    class Meta:
        model = Quiz
        fields = [
            "course",
            "title",
            "instructions",
            "available_from",
            "available_to",
            "duration_minutes",
            "total_marks",
            "pass_percentage",
            "max_attempts",
            "shuffle_questions",
            "shuffle_options",
            "release_correct_answers",
            "status",
        ]
        widgets = {
            "available_from": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"}
            ),
            "available_to": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"}
            ),
            "instructions": forms.Textarea(
                attrs={"rows": 4, "placeholder": "Specify quiz rules, academic honesty instructions, permitted formulas..."}
            ),
            "duration_minutes": forms.NumberInput(attrs={"min": 1, "max": 360}),
            "pass_percentage": forms.NumberInput(attrs={"min": 0, "max": 100, "step": "0.1"}),
            "total_marks": forms.NumberInput(attrs={"min": 0, "step": "0.5"}),
            "max_attempts": forms.NumberInput(attrs={"min": 1, "max": 10}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        # Filter courses to only those allocated to the active lecturer (unless Admin)
        if user and not (user.is_admin_role or user.is_superuser):
            allocated_course_ids = CourseAllocation.objects.filter(
                lecturer=user,
                is_active=True,
            ).values_list("course_id", flat=True)
            self.fields["course"].queryset = Course.objects.filter(
                id__in=allocated_course_ids,
                is_active=True,
            ).order_by("code")

        # Set default values for dates if empty
        self.fields["course"].empty_label = "Select an Allocated Course"

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get("available_from")
        end = cleaned_data.get("available_to")
        status = cleaned_data.get("status")

        if start and end and start >= end:
            self.add_error(
                "available_to",
                "The availability closing time must be chronologically after the opening time.",
            )

        # Validation when publishing
        if status == QuizStatus.PUBLISHED and self.instance.pk:
            q_count = self.instance.questions.count()
            if q_count == 0:
                self.add_error(
                    "status",
                    "A quiz must contain at least one question before it can be published.",
                )

        return cleaned_data


class QuestionForm(forms.ModelForm):
    """Form to create or update an individual question."""

    class Meta:
        model = Question
        fields = [
            "text",
            "question_type",
            "marks",
            "order",
            "model_answer",
        ]
        widgets = {
            "text": forms.Textarea(attrs={"rows": 3, "placeholder": "Enter the question prompt here..."}),
            "model_answer": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Enter model answer, scoring rubric, or rationale for evaluation/feedback...",
                }
            ),
            "marks": forms.NumberInput(attrs={"min": "0.1", "step": "0.5"}),
            "order": forms.NumberInput(attrs={"min": 1}),
        }


class BaseQuestionOptionFormSet(forms.BaseInlineFormSet):
    """Custom formset validator ensuring valid options structure."""

    def clean(self):
        super().clean()
        if any(self.errors):
            return

        question_type = getattr(self.instance, "question_type", None)
        valid_options = []
        correct_count = 0

        for form in self.forms:
            if self.can_delete and self._should_delete_form(form):
                continue
            if form.cleaned_data.get("text"):
                valid_options.append(form.cleaned_data)
                if form.cleaned_data.get("is_correct"):
                    correct_count += 1

        if question_type == QuestionType.MULTIPLE_CHOICE:
            if len(valid_options) < 2:
                raise ValidationError("Multiple-choice questions must have at least 2 non-empty options.")
            if correct_count != 1:
                raise ValidationError(
                    f"Multiple-choice questions must have exactly one correct option. Currently {correct_count} selected."
                )
        elif question_type == QuestionType.TRUE_FALSE:
            if len(valid_options) != 2:
                raise ValidationError("True/False questions must have exactly 2 options ('True' and 'False').")
            if correct_count != 1:
                raise ValidationError("True/False questions must have exactly one correct option.")


QuestionOptionFormSet = inlineformset_factory(
    Question,
    QuestionOption,
    fields=["text", "is_correct", "order"],
    extra=4,
    can_delete=True,
    formset=BaseQuestionOptionFormSet,
    widgets={
        "text": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Option text"}),
        "is_correct": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        "order": forms.NumberInput(attrs={"class": "form-control form-control-sm", "min": 1}),
    },
)


class ShortAnswerEvaluationForm(forms.Form):
    """Form used by lecturers to grade a single short-answer response."""

    marks_awarded = forms.DecimalField(
        max_digits=5,
        decimal_places=2,
        min_value=Decimal("0.00"),
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "step": "0.25"}),
        label="Marks Awarded",
    )
    lecturer_comment = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={"class": "form-control form-control-sm", "rows": 2, "placeholder": "Feedback or rubric notes for the student..."}
        ),
        label="Feedback / Rubric Commentary",
    )

    def __init__(self, *args, max_marks=Decimal("1.00"), **kwargs):
        super().__init__(*args, **kwargs)
        self.max_marks = max_marks
        self.fields["marks_awarded"].widget.attrs["max"] = str(max_marks)

    def clean_marks_awarded(self):
        marks = self.cleaned_data.get("marks_awarded")
        if marks is not None and marks > self.max_marks:
            raise ValidationError(f"Marks awarded ({marks}) cannot exceed maximum question marks ({self.max_marks}).")
        return marks
