"""Forms for Rule-Based Smart Academic Workload Planner."""
from decimal import Decimal
from django import forms
from django.core.exceptions import ValidationError

from .models import StudentStudyBudget


class StudentStudyBudgetForm(forms.ModelForm):
    """Form allowing enrolled students to configure their weekly available study hours."""

    class Meta:
        model = StudentStudyBudget
        fields = [
            "monday_hours",
            "tuesday_hours",
            "wednesday_hours",
            "thursday_hours",
            "friday_hours",
            "saturday_hours",
            "sunday_hours",
            "notes",
        ]
        widgets = {
            "monday_hours": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.5",
                    "min": "0.0",
                    "max": "24.0",
                    "placeholder": "e.g. 2.0",
                }
            ),
            "tuesday_hours": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.5",
                    "min": "0.0",
                    "max": "24.0",
                    "placeholder": "e.g. 2.0",
                }
            ),
            "wednesday_hours": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.5",
                    "min": "0.0",
                    "max": "24.0",
                    "placeholder": "e.g. 2.0",
                }
            ),
            "thursday_hours": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.5",
                    "min": "0.0",
                    "max": "24.0",
                    "placeholder": "e.g. 2.0",
                }
            ),
            "friday_hours": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.5",
                    "min": "0.0",
                    "max": "24.0",
                    "placeholder": "e.g. 2.0",
                }
            ),
            "saturday_hours": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.5",
                    "min": "0.0",
                    "max": "24.0",
                    "placeholder": "e.g. 4.0",
                }
            ),
            "sunday_hours": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.5",
                    "min": "0.0",
                    "max": "24.0",
                    "placeholder": "e.g. 4.0",
                }
            ),
            "notes": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g. 'Concentrate on weekend study sessions', 'Part-time work on Thursdays'",
                }
            ),
        }
        labels = {
            "monday_hours": "Monday Available Hours",
            "tuesday_hours": "Tuesday Available Hours",
            "wednesday_hours": "Wednesday Available Hours",
            "thursday_hours": "Thursday Available Hours",
            "friday_hours": "Friday Available Hours",
            "saturday_hours": "Saturday Available Hours",
            "sunday_hours": "Sunday Available Hours",
            "notes": "Personal Study Constraints / Notes",
        }

    def clean(self):
        cleaned_data = super().clean()
        total = Decimal("0.0")
        for day in [
            "monday_hours",
            "tuesday_hours",
            "wednesday_hours",
            "thursday_hours",
            "friday_hours",
            "saturday_hours",
            "sunday_hours",
        ]:
            val = cleaned_data.get(day)
            if val is not None:
                if val < Decimal("0.0"):
                    self.add_error(day, "Study hours cannot be negative.")
                if val > Decimal("24.0"):
                    self.add_error(day, "Study hours for a single day cannot exceed 24 hours.")
                total += val

        if total > Decimal("168.0"):
            raise ValidationError("Total weekly study hours cannot exceed 168 hours.")

        return cleaned_data
