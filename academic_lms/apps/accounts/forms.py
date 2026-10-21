"""Authentication and profile forms for Academic LMS."""
from django import forms
from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError
from .models import (
    User,
    Role,
    StudentProfile,
    LecturerProfile,
    ParentProfile,
    ParentStudentRelationship,
)


class LoginForm(forms.Form):
    """Email and password authentication form."""

    email = forms.EmailField(
        label="Email Address",
        widget=forms.EmailInput(
            attrs={
                "class": "form-control form-control-academic",
                "placeholder": "e.g. user@gmail.com",
                "autocomplete": "email",
                "autofocus": True,
            }
        ),
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control form-control-academic",
                "placeholder": "Enter your password",
                "autocomplete": "current-password",
            }
        ),
    )

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get("email")
        password = cleaned_data.get("password")

        if email and password:
            email = email.lower().strip()
            # Standard Django ModelBackend matches USERNAME_FIELD ("email") passed as username
            self.user = authenticate(username=email, password=password)
            if self.user is None:
                raise ValidationError("Invalid email address or password. Please verify your credentials.")
            if not self.user.is_active:
                raise ValidationError("This account is currently disabled. Please contact your institution administrator.")

        return cleaned_data

    def get_user(self):
        return getattr(self, "user", None)


class UserProfileUpdateForm(forms.ModelForm):
    """Permitted profile editing form for users.

    Strictly protects against unauthorized privilege escalation or role tampering.
    """

    class Meta:
        model = User
        fields = ["first_name", "last_name", "username"]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control form-control-academic"}),
            "last_name": forms.TextInput(attrs={"class": "form-control form-control-academic"}),
            "username": forms.TextInput(attrs={"class": "form-control form-control-academic"}),
        }

    def clean_username(self):
        username = self.cleaned_data.get("username")
        qs = User.objects.filter(username=username).exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("This username is already taken. Please choose another.")
        return username


class StudentProfileUpdateForm(forms.ModelForm):
    """Permitted student profile details editing."""

    class Meta:
        model = StudentProfile
        fields = ["phone", "emergency_contact", "date_of_birth"]
        widgets = {
            "phone": forms.TextInput(attrs={"class": "form-control form-control-academic"}),
            "emergency_contact": forms.TextInput(attrs={"class": "form-control form-control-academic"}),
            "date_of_birth": forms.DateInput(attrs={"class": "form-control form-control-academic", "type": "date"}),
        }


class LecturerProfileUpdateForm(forms.ModelForm):
    """Permitted lecturer profile details editing."""

    class Meta:
        model = LecturerProfile
        fields = ["office_location", "phone"]
        widgets = {
            "office_location": forms.TextInput(attrs={"class": "form-control form-control-academic"}),
            "phone": forms.TextInput(attrs={"class": "form-control form-control-academic"}),
        }


class ParentProfileUpdateForm(forms.ModelForm):
    """Permitted parent profile details editing."""

    class Meta:
        model = ParentProfile
        fields = ["phone", "address"]
        widgets = {
            "phone": forms.TextInput(attrs={"class": "form-control form-control-academic"}),
            "address": forms.TextInput(attrs={"class": "form-control form-control-academic"}),
        }


class ParentStudentRelationshipForm(forms.ModelForm):
    """Administrator form for linking parent and student accounts."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["parent"].queryset = User.objects.filter(role=Role.PARENT, is_active=True)
        self.fields["student"].queryset = User.objects.filter(role=Role.STUDENT, is_active=True)
        self.fields["parent"].widget.attrs.update({"class": "form-select form-select-academic"})
        self.fields["student"].widget.attrs.update({"class": "form-select form-select-academic"})
        self.fields["relationship_type"].widget.attrs.update({"class": "form-select form-select-academic"})

    class Meta:
        model = ParentStudentRelationship
        fields = ["parent", "student", "relationship_type"]
