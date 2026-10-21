"""Forms for Courseware and Learning Resource Management."""
from django import forms
from django.core.exceptions import ValidationError
from apps.academics.models import Course, CourseAllocation
from .models import LearningResource, CourseModule, ResourceType, ResourceStatus
from .validators import validate_resource_file, validate_resource_url


class LearningResourceForm(forms.ModelForm):
    """Form for creating and editing learning resources."""

    class Meta:
        model = LearningResource
        fields = [
            "course",
            "module",
            "title",
            "description",
            "resource_type",
            "status",
            "file",
            "external_url",
        ]
        widgets = {
            "course": forms.Select(attrs={"class": "form-select"}),
            "module": forms.Select(attrs={"class": "form-select"}),
            "title": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "e.g. Lecture 1: Database Normalization"}
            ),
            "description": forms.Textarea(
                attrs={"class": "form-control", "rows": 4, "placeholder": "Summary or reading guidance..."}
            ),
            "resource_type": forms.Select(attrs={"class": "form-select"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "file": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "external_url": forms.URLInput(
                attrs={"class": "form-control", "placeholder": "https://example.com/material"}
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

        # Dynamic course choices scoping
        if user and not user.is_admin_role:
            # Lecturers only see courses allocated to them
            allocated_courses = Course.objects.filter(
                allocations__lecturer=user,
                allocations__is_active=True,
                is_active=True,
            ).distinct()
            self.fields["course"].queryset = allocated_courses
        else:
            self.fields["course"].queryset = Course.objects.filter(is_active=True)

        # Module queryset scoping
        course_id = None
        if self.instance and self.instance.pk and self.instance.course_id:
            course_id = self.instance.course_id
        elif "course" in self.data:
            try:
                course_id = int(self.data.get("course"))
            except (ValueError, TypeError):
                pass

        if course_id:
            self.fields["module"].queryset = CourseModule.objects.filter(
                course_id=course_id, is_active=True
            ).order_by("order", "id")
        else:
            self.fields["module"].queryset = CourseModule.objects.filter(is_active=True)

        self.fields["module"].empty_label = "(Optional) No Module / General Course Material"

    def clean(self):
        cleaned_data = super().clean()
        course = cleaned_data.get("course")
        module = cleaned_data.get("module")
        r_type = cleaned_data.get("resource_type")
        file = cleaned_data.get("file")
        url = cleaned_data.get("external_url")

        # 1. Verify user is authorized to manage the selected course
        if self.user and not self.user.is_admin_role and course:
            is_allocated = CourseAllocation.objects.filter(
                course=course,
                lecturer=self.user,
                is_active=True,
            ).exists()
            if not is_allocated:
                self.add_error("course", "You are not authorized to create or edit resources for this course.")

        # 2. Module must belong to the chosen course
        if module and course and module.course_id != course.id:
            self.add_error("module", "The selected module does not belong to the selected course.")

        # 3. Resource type specifics
        if r_type in [ResourceType.EXTERNAL_LINK, ResourceType.VIDEO_LINK]:
            if not url:
                self.add_error("external_url", "External link or video link requires a valid URL.")
            elif url:
                try:
                    validate_resource_url(url)
                except ValidationError as e:
                    self.add_error("external_url", e)

        if r_type in [ResourceType.DOCUMENT, ResourceType.PRESENTATION]:
            if not file and not url and not (self.instance and self.instance.file):
                self.add_error(
                    "file",
                    "Please upload a document file or supply an external resource URL.",
                )

        if file:
            try:
                validate_resource_file(file)
            except ValidationError as e:
                self.add_error("file", e)

        return cleaned_data


class CourseModuleForm(forms.ModelForm):
    """Form to create or edit course topic modules."""

    class Meta:
        model = CourseModule
        fields = ["course", "title", "description", "order"]
        widgets = {
            "course": forms.Select(attrs={"class": "form-select"}),
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Week 2: Data Modeling"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Module description"}),
            "order": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        if user and not user.is_admin_role:
            self.fields["course"].queryset = Course.objects.filter(
                allocations__lecturer=user,
                allocations__is_active=True,
                is_active=True,
            ).distinct()
        else:
            self.fields["course"].queryset = Course.objects.filter(is_active=True)
