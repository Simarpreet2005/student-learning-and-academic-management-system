"""Custom User and Profile models for Academic LMS.

Enforces strict role-based definitions, email-based authentication,
profile separation, and validated parent-student relationships.
"""
from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Role(models.TextChoices):
    """Primary user role designations."""
    ADMIN = "ADMIN", "Administrator"
    LECTURER = "LECTURER", "Lecturer"
    STUDENT = "STUDENT", "Student"
    PARENT = "PARENT", "Parent"


class UserManager(BaseUserManager):
    """Custom manager for User model where email is the unique identifier."""

    def create_user(
        self,
        email: str,
        username: str,
        password: str = None,
        role: str = Role.STUDENT,
        **extra_fields,
    ):
        """Create and save a standard User with the given email, username, and password."""
        if not email:
            raise ValueError("The Email field must be set.")
        if not username:
            raise ValueError("The Username field must be set.")

        email = self.normalize_email(email).lower()
        extra_fields.setdefault("is_active", True)

        # Ensure correct staff status for Admin role
        if role == Role.ADMIN:
            extra_fields.setdefault("is_staff", True)
        else:
            extra_fields.setdefault("is_staff", False)

        user = self.model(
            email=email,
            username=username,
            role=role,
            **extra_fields,
        )
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(
        self,
        email: str,
        username: str,
        password: str = None,
        **extra_fields,
    ):
        """Create and save a Superuser with admin privileges."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", Role.ADMIN)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(
            email=email,
            username=username,
            password=password,
            **extra_fields,
        )


class User(AbstractBaseUser, PermissionsMixin):
    """Custom User model using email as unique login identifier."""

    email = models.EmailField(
        unique=True,
        max_length=255,
        verbose_name="Email Address",
        help_text="Primary email address used for system login.",
    )
    username = models.CharField(
        unique=True,
        max_length=150,
        verbose_name="Username",
        help_text="Unique display identifier.",
    )
    first_name = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="First Name",
    )
    last_name = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="Last Name",
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.STUDENT,
        verbose_name="System Role",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Active",
        help_text="Designates whether this user account should be treated as active.",
    )
    is_staff = models.BooleanField(
        default=False,
        verbose_name="Staff Status",
        help_text="Designates whether the user can log into the Django admin site.",
    )
    date_joined = models.DateTimeField(
        default=timezone.now,
        verbose_name="Date Joined",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Last Updated",
    )

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        ordering = ["-date_joined"]

    def __str__(self) -> str:
        return f"{self.username} ({self.get_role_display()})"

    @property
    def get_full_name(self) -> str:
        full_name = f"{self.first_name} {self.last_name}".strip()
        return full_name or self.username or self.email

    @property
    def get_short_name(self) -> str:
        return self.first_name or self.username or self.email

    @property
    def is_admin_role(self) -> bool:
        return self.role == Role.ADMIN or self.is_staff or self.is_superuser

    @property
    def is_lecturer_role(self) -> bool:
        return self.role == Role.LECTURER

    @property
    def is_student_role(self) -> bool:
        return self.role == Role.STUDENT

    @property
    def is_parent_role(self) -> bool:
        return self.role == Role.PARENT

    def clean(self):
        super().clean()
        if self.email:
            self.email = self.email.lower()
        # Maintain consistency between role and staff/superuser permissions
        if self.is_superuser and self.role != Role.ADMIN:
            self.role = Role.ADMIN
            self.is_staff = True


class StudentProfile(models.Model):
    """Academic and profile details for enrolled students."""

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="student_profile",
        limit_choices_to={"role": Role.STUDENT},
    )
    student_id = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Student ID",
        help_text="Institutional registration number (e.g. STD-2026-0001).",
    )
    program = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="Academic Program",
        help_text="Enrolled degree or department program.",
    )
    current_semester = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Current Semester",
    )
    phone = models.CharField(
        max_length=30,
        blank=True,
        verbose_name="Phone Number",
    )
    emergency_contact = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="Emergency Contact",
    )
    date_of_birth = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date of Birth",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Student Profile"
        verbose_name_plural = "Student Profiles"

    def __str__(self) -> str:
        return f"{self.student_id} — {self.user.get_full_name}"

    def clean(self):
        if self.user.role != Role.STUDENT:
            raise ValidationError("StudentProfile can only be associated with a user having the STUDENT role.")


class LecturerProfile(models.Model):
    """Academic and professional details for teaching faculty."""

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="lecturer_profile",
        limit_choices_to={"role": Role.LECTURER},
    )
    employee_id = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Employee / Staff ID",
        help_text="Institutional staff number (e.g. LEC-2026-0001).",
    )
    department = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="Academic Department",
    )
    office_location = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Office Location",
    )
    phone = models.CharField(
        max_length=30,
        blank=True,
        verbose_name="Office Phone",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Lecturer Profile"
        verbose_name_plural = "Lecturer Profiles"

    def __str__(self) -> str:
        return f"{self.employee_id} — {self.user.get_full_name}"

    def clean(self):
        if self.user.role != Role.LECTURER:
            raise ValidationError("LecturerProfile can only be associated with a user having the LECTURER role.")


class ParentProfile(models.Model):
    """Contact details for authorized legal guardians."""

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="parent_profile",
        limit_choices_to={"role": Role.PARENT},
    )
    phone = models.CharField(
        max_length=30,
        blank=True,
        verbose_name="Contact Phone",
    )
    address = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Residential Address",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Parent Profile"
        verbose_name_plural = "Parent Profiles"

    def __str__(self) -> str:
        return f"Parent: {self.user.get_full_name}"

    def clean(self):
        if self.user.role != Role.PARENT:
            raise ValidationError("ParentProfile can only be associated with a user having the PARENT role.")


class RelationshipType(models.TextChoices):
    """Allowed parent-student relationship categories."""
    FATHER = "FATHER", "Father"
    MOTHER = "MOTHER", "Mother"
    GUARDIAN = "GUARDIAN", "Legal Guardian"
    OTHER = "OTHER", "Other"


class ParentStudentRelationship(models.Model):
    """Explicit mapping linking a parent user to a student user.

    Strictly manages authorized observer access. Only administrators can
    create or remove these links.
    """

    parent = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="parent_relationships",
        limit_choices_to={"role": Role.PARENT},
        verbose_name="Parent User",
    )
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="student_relationships",
        limit_choices_to={"role": Role.STUDENT},
        verbose_name="Student User",
    )
    relationship_type = models.CharField(
        max_length=30,
        choices=RelationshipType.choices,
        default=RelationshipType.GUARDIAN,
        verbose_name="Relationship Type",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Parent–Student Relationship"
        verbose_name_plural = "Parent–Student Relationships"
        constraints = [
            models.UniqueConstraint(
                fields=["parent", "student"],
                name="unique_parent_student_relationship",
            )
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.parent.get_full_name} -> {self.student.get_full_name} ({self.get_relationship_type_display()})"

    def clean(self):
        super().clean()
        if self.parent_id and self.student_id:
            if self.parent_id == self.student_id:
                raise ValidationError("Parent and student cannot be the same user account.")
            if self.parent.role != Role.PARENT:
                raise ValidationError("The parent in this relationship must have the PARENT role.")
            if self.student.role != Role.STUDENT:
                raise ValidationError("The student in this relationship must have the STUDENT role.")
