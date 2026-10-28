"""Forms for assignment creation, submission, and grading."""
from django import forms
from django.core.exceptions import ValidationError

from apps.academics.models import Course
from apps.courseware.validators import validate_resource_file
from .models import Assignment, AssignmentSubmission


class AssignmentForm(forms.ModelForm):
    class Meta:
        model = Assignment
        fields = (
            "course", "title", "description", "due_date", "cutoff_date",
            "maximum_marks", "estimated_effort_hours", "is_published",
        )
        widgets = {
            "course": forms.Select(attrs={"class": "form-select"}),
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 5}),
            "due_date": forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
            "cutoff_date": forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
            "maximum_marks": forms.NumberInput(attrs={"class": "form-control", "min": "0.01", "step": "0.01"}),
            "estimated_effort_hours": forms.NumberInput(attrs={"class": "form-control", "min": "0.1", "step": "0.1"}),
            "is_published": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        courses = Course.objects.filter(is_active=True)
        if user.is_lecturer_role:
            courses = courses.filter(allocations__lecturer=user, allocations__is_active=True)
        self.fields["course"].queryset = courses.distinct()

    def clean(self):
        cleaned = super().clean()
        due_date = cleaned.get("due_date")
        cutoff_date = cleaned.get("cutoff_date")
        if due_date and cutoff_date and cutoff_date < due_date:
            self.add_error("cutoff_date", "The cutoff cannot be earlier than the due date.")
        return cleaned


class AssignmentSubmissionForm(forms.ModelForm):
    class Meta:
        model = AssignmentSubmission
        fields = ("submission_notes", "submission_file")
        widgets = {
            "submission_notes": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "submission_file": forms.ClearableFileInput(attrs={"class": "form-control"}),
        }

    def clean_submission_file(self):
        uploaded = self.cleaned_data.get("submission_file")
        if uploaded:
            validate_resource_file(uploaded)
        return uploaded

    def clean(self):
        cleaned = super().clean()
        notes = cleaned.get("submission_notes", "").strip()
        uploaded = cleaned.get("submission_file")
        if not notes and not uploaded:
            raise ValidationError("Add submission notes or attach a file before submitting.")
        return cleaned


class AssignmentGradeForm(forms.ModelForm):
    class Meta:
        model = AssignmentSubmission
        fields = ("score", "lecturer_feedback")
        widgets = {
            "score": forms.NumberInput(attrs={"class": "form-control", "min": "0", "step": "0.01"}),
            "lecturer_feedback": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["score"].widget.attrs["max"] = str(self.instance.assignment.maximum_marks)

    def clean_score(self):
        score = self.cleaned_data.get("score")
        if score is None or score < 0 or score > self.instance.assignment.maximum_marks:
            raise ValidationError(f"Enter a score from 0 to {self.instance.assignment.maximum_marks}.")
        return score
