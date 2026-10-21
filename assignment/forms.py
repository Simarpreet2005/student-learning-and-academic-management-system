from decimal import Decimal
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from .models import Assignment, AssignmentSubmission

MAX_FILE_SIZE_MB = 15
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


class AssignmentForm(forms.ModelForm):
    start_date = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local", "class": "form-control"}
        ),
        label=_("Start / Open Date"),
        help_text=_("Optional date & time when the assignment opens for submissions"),
    )
    due_date = forms.DateTimeField(
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local", "class": "form-control"}
        ),
        label=_("Due Date & Time"),
        help_text=_("Select the submission deadline date and time"),
    )

    class Meta:
        model = Assignment
        fields = [
            "title",
            "description",
            "start_date",
            "due_date",
            "maximum_marks",
            "file",
            "allow_resubmission",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].widget.attrs.update(
            {"class": "form-control", "placeholder": _("Assignment title")}
        )
        self.fields["description"].widget.attrs.update(
            {
                "class": "form-control",
                "rows": 5,
                "placeholder": _("Enter detailed assignment instructions and requirements..."),
            }
        )
        self.fields["maximum_marks"].widget.attrs.update(
            {"class": "form-control", "min": "0.01", "step": "0.5"}
        )
        self.fields["file"].widget.attrs.update({"class": "form-control"})
        self.fields["allow_resubmission"].widget.attrs.update(
            {"class": "form-check-input"}
        )

        # Prepopulate datetime-local values if editing existing instance
        if self.instance and self.instance.pk:
            if self.instance.start_date:
                self.initial["start_date"] = self.instance.start_date.strftime(
                    "%Y-%m-%dT%H:%M"
                )
            if self.instance.due_date:
                self.initial["due_date"] = self.instance.due_date.strftime(
                    "%Y-%m-%dT%H:%M"
                )

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        due_date = cleaned_data.get("due_date")
        if start_date and due_date and start_date >= due_date:
            self.add_error("start_date", _("Start date must be before due date."))
        return cleaned_data

    def clean_maximum_marks(self):
        maximum_marks = self.cleaned_data.get("maximum_marks")
        if maximum_marks is not None and maximum_marks <= Decimal("0.00"):
            raise ValidationError(_("Maximum marks must be greater than zero."))
        return maximum_marks

    def clean_file(self):
        uploaded_file = self.cleaned_data.get("file")
        if uploaded_file and hasattr(uploaded_file, "size"):
            if uploaded_file.size > MAX_FILE_SIZE_BYTES:
                raise ValidationError(
                    _(f"File size exceeds the maximum allowed limit of {MAX_FILE_SIZE_MB}MB.")
                )
        return uploaded_file


class AssignmentSubmissionForm(forms.ModelForm):
    class Meta:
        model = AssignmentSubmission
        fields = ["file", "comment"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["file"].widget.attrs.update({"class": "form-control"})
        self.fields["comment"].widget.attrs.update(
            {
                "class": "form-control",
                "rows": 3,
                "placeholder": _("Optional comments or notes for your lecturer..."),
            }
        )

    def clean_file(self):
        uploaded_file = self.cleaned_data.get("file")
        if uploaded_file and hasattr(uploaded_file, "size"):
            if uploaded_file.size > MAX_FILE_SIZE_BYTES:
                raise ValidationError(
                    _(f"File size exceeds the maximum allowed limit of {MAX_FILE_SIZE_MB}MB.")
                )
        return uploaded_file


class SubmissionGradeForm(forms.ModelForm):
    class Meta:
        model = AssignmentSubmission
        fields = ["marks", "feedback"]

    def __init__(self, *args, assignment=None, **kwargs):
        self.assignment = assignment
        super().__init__(*args, **kwargs)
        if not self.assignment and self.instance and hasattr(self.instance, "assignment"):
            self.assignment = self.instance.assignment

        max_marks_str = str(self.assignment.maximum_marks) if self.assignment else "100"
        self.fields["marks"].widget.attrs.update(
            {
                "class": "form-control",
                "min": "0",
                "max": max_marks_str,
                "step": "0.5",
                "placeholder": f"Max: {max_marks_str}",
            }
        )
        self.fields["feedback"].widget.attrs.update(
            {
                "class": "form-control",
                "rows": 4,
                "placeholder": _("Provide constructive feedback for the student..."),
            }
        )

    def clean_marks(self):
        marks = self.cleaned_data.get("marks")
        if marks is not None:
            if marks < Decimal("0.00"):
                raise ValidationError(_("Marks cannot be negative."))
            if self.assignment and marks > self.assignment.maximum_marks:
                err_msg = (
                    f"Marks cannot exceed the assignment maximum of "
                    f"{self.assignment.maximum_marks}."
                )
                raise ValidationError(_(err_msg))
        return marks
