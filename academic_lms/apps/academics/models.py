"""Academic hierarchy, curricula, course offerings, allocations, and enrollments."""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Department(models.Model):
    """Academic Department (e.g. Department of Computer Science)."""

    name = models.CharField(max_length=150, unique=True, verbose_name="Department Name")
    code = models.CharField(max_length=20, unique=True, verbose_name="Department Code")
    description = models.TextField(blank=True, verbose_name="Description")
    is_active = models.BooleanField(default=True, verbose_name="Active Status")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Department"
        verbose_name_plural = "Departments"
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class AcademicProgram(models.Model):
    """Degree program (e.g. B.Sc. Computer Science)."""

    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name="programs",
        verbose_name="Department",
    )
    name = models.CharField(max_length=150, verbose_name="Program Name")
    code = models.CharField(max_length=20, unique=True, verbose_name="Program Code")
    description = models.TextField(blank=True, verbose_name="Description")
    is_active = models.BooleanField(default=True, verbose_name="Active Status")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Academic Program"
        verbose_name_plural = "Academic Programs"
        ordering = ["department", "name"]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class AcademicYear(models.Model):
    """Academic calendar session (e.g. 2026/2027)."""

    name = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Academic Year",
        help_text="e.g. 2026/2027",
    )
    start_date = models.DateField(verbose_name="Start Date")
    end_date = models.DateField(verbose_name="End Date")
    is_current = models.BooleanField(default=False, verbose_name="Current Academic Year")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Academic Year"
        verbose_name_plural = "Academic Years"
        ordering = ["-start_date"]

    def __str__(self) -> str:
        current_marker = " (Current)" if self.is_current else ""
        return f"{self.name}{current_marker}"

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.start_date >= self.end_date:
            raise ValidationError({"end_date": "End date must be chronologically after start date."})

    def save(self, *args, **kwargs):
        if self.is_current:
            # Ensure only one academic year is marked current
            AcademicYear.objects.filter(is_current=True).exclude(pk=self.pk).update(is_current=False)
        super().save(*args, **kwargs)


class SemesterType(models.TextChoices):
    FIRST = "FIRST", "First Semester"
    SECOND = "SECOND", "Second Semester"
    SUMMER = "SUMMER", "Summer Session"


class Semester(models.Model):
    """Academic semester division within an Academic Year."""

    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name="semesters",
        verbose_name="Academic Year",
    )
    name = models.CharField(
        max_length=100,
        verbose_name="Semester Name",
        help_text="e.g. Fall 2026",
    )
    semester_type = models.CharField(
        max_length=20,
        choices=SemesterType.choices,
        default=SemesterType.FIRST,
        verbose_name="Semester Type",
    )
    start_date = models.DateField(verbose_name="Start Date")
    end_date = models.DateField(verbose_name="End Date")
    is_active = models.BooleanField(default=True, verbose_name="Active Semester")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Semester"
        verbose_name_plural = "Semesters"
        ordering = ["-start_date"]

    def __str__(self) -> str:
        return f"{self.name} ({self.academic_year.name})"

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.start_date >= self.end_date:
            raise ValidationError({"end_date": "End date must be after start date."})
        if self.academic_year_id and self.start_date and self.end_date:
            if self.start_date < self.academic_year.start_date or self.end_date > self.academic_year.end_date:
                raise ValidationError("Semester dates must fall within the academic year boundary.")


class Course(models.Model):
    """Institutional course curriculum offering."""

    code = models.CharField(
        max_length=20,
        unique=True,
        db_index=True,
        verbose_name="Course Code",
        help_text="e.g. CS101, ENG202",
    )
    title = models.CharField(max_length=200, verbose_name="Course Title")
    description = models.TextField(blank=True, verbose_name="Course Description")
    credits = models.PositiveIntegerField(default=3, verbose_name="Credit Units")
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="courses",
        verbose_name="Department",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Active Status",
        help_text="Soft deactivation toggle",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Course"
        verbose_name_plural = "Courses"
        ordering = ["code"]

    def __str__(self) -> str:
        return f"{self.code} — {self.title}"

    def clean(self):
        super().clean()
        if self.code:
            self.code = self.code.strip().upper()


class CourseAllocation(models.Model):
    """Official allocation binding a course to an assigned lecturer."""

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="allocations",
        verbose_name="Course",
    )
    lecturer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="course_allocations",
        limit_choices_to={"role": "LECTURER"},
        verbose_name="Allocated Lecturer",
    )
    semester = models.ForeignKey(
        Semester,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="allocations",
        verbose_name="Semester",
    )
    is_active = models.BooleanField(default=True, verbose_name="Active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Course Allocation"
        verbose_name_plural = "Course Allocations"
        constraints = [
            models.UniqueConstraint(
                fields=["course", "lecturer", "semester"],
                name="unique_course_lecturer_semester_allocation",
            )
        ]
        ordering = ["course", "lecturer"]

    def __str__(self) -> str:
        sem = f" ({self.semester.name})" if self.semester else ""
        return f"{self.course.code} -> {self.lecturer.get_full_name}{sem}"


class EnrollmentStatus(models.TextChoices):
    ENROLLED = "ENROLLED", "Enrolled"
    DROPPED = "DROPPED", "Dropped"
    COMPLETED = "COMPLETED", "Completed"


class StudentEnrollment(models.Model):
    """Official course registration for an enrolled student."""

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="enrollments",
        limit_choices_to={"role": "STUDENT"},
        verbose_name="Student",
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="enrollments",
        verbose_name="Course",
    )
    semester = models.ForeignKey(
        Semester,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="enrollments",
        verbose_name="Semester",
    )
    status = models.CharField(
        max_length=20,
        choices=EnrollmentStatus.choices,
        default=EnrollmentStatus.ENROLLED,
        verbose_name="Enrollment Status",
    )
    is_active = models.BooleanField(default=True, verbose_name="Active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Student Enrollment"
        verbose_name_plural = "Student Enrollments"
        constraints = [
            models.UniqueConstraint(
                fields=["student", "course", "semester"],
                name="unique_student_course_semester_enrollment",
            )
        ]
        ordering = ["course", "student"]

    def __str__(self) -> str:
        sem = f" [{self.semester.name}]" if self.semester else ""
        return f"{self.student.get_full_name} -> {self.course.code} ({self.get_status_display()}){sem}"
