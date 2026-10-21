"""Permission evaluation helpers for Quizzes, Questions, Attempts, and Results.

Strict server-side role and object-level boundaries:
- Admin: Institutional oversight across all courses and quizzes.
- Lecturer: Manage quizzes and grade attempts only for officially allocated courses.
- Student: Attempt published quizzes during valid windows and inspect own results.
- Parent: Strictly read-only access to results for explicitly linked students only.
"""
from django.db.models import QuerySet
from django.utils import timezone

from apps.accounts.models import ParentStudentRelationship, Role
from apps.academics.models import Course, CourseAllocation, StudentEnrollment
from .models import AttemptStatus, Quiz, QuizAttempt, QuizStatus


def can_view_quiz(user, quiz: Quiz) -> bool:
    """Check if the user is authorized to view quiz information and syllabus listing."""
    if not user or not user.is_authenticated or not quiz or not quiz.is_active:
        return False

    # 1. Administrator oversight
    if user.is_admin_role or user.is_superuser:
        return True

    # 2. Lecturer: Must be allocated to the course
    if user.is_lecturer_role:
        return CourseAllocation.objects.filter(
            course=quiz.course,
            lecturer=user,
            is_active=True,
        ).exists()

    # 3. Student: Must be enrolled and quiz must be published
    if user.is_student_role:
        if quiz.status != QuizStatus.PUBLISHED:
            return False
        return StudentEnrollment.objects.filter(
            course=quiz.course,
            student=user,
            is_active=True,
            status="ENROLLED",
        ).exists()

    # 4. Parent: Must have a linked student enrolled and quiz must be published
    if user.is_parent_role:
        if quiz.status != QuizStatus.PUBLISHED:
            return False
        linked_student_ids = ParentStudentRelationship.objects.filter(
            parent=user
        ).values_list("student_id", flat=True)
        return StudentEnrollment.objects.filter(
            course=quiz.course,
            student_id__in=linked_student_ids,
            is_active=True,
            status="ENROLLED",
        ).exists()

    return False


def can_manage_quiz(user, quiz: Quiz = None, course: Course = None) -> bool:
    """Check if the user can create, edit, publish, or delete a quiz or its questions."""
    if not user or not user.is_authenticated:
        return False

    if user.is_admin_role or user.is_superuser:
        return True

    if user.is_lecturer_role:
        target_course = course or (quiz.course if quiz else None)
        if not target_course:
            return False
        return CourseAllocation.objects.filter(
            course=target_course,
            lecturer=user,
            is_active=True,
        ).exists()

    return False


def can_attempt_quiz(user, quiz: Quiz) -> tuple[bool, str]:
    """Check if a student can start or resume a quiz attempt.

    Returns a tuple of (can_attempt: bool, reason_message: str).
    """
    if not user or not user.is_authenticated:
        return False, "You must be signed in to attempt a quiz."

    if not user.is_student_role:
        return False, "Only registered students are permitted to take quizzes."

    if not quiz or not quiz.is_active or quiz.status != QuizStatus.PUBLISHED:
        return False, "This quiz is not currently published or active."

    # Verify course enrollment
    is_enrolled = StudentEnrollment.objects.filter(
        course=quiz.course,
        student=user,
        is_active=True,
        status="ENROLLED",
    ).exists()
    if not is_enrolled:
        return False, "You must be officially enrolled in this course to take this quiz."

    # Check for an active in-progress attempt
    active_attempt = QuizAttempt.objects.filter(
        quiz=quiz,
        student=user,
        status=AttemptStatus.IN_PROGRESS,
    ).first()
    if active_attempt:
        # Check if the existing attempt expired
        if active_attempt.is_time_expired():
            return False, "Your existing attempt has elapsed its allotted duration."
        return True, "Resume in-progress attempt."

    # Check availability window
    now = timezone.now()
    if now < quiz.available_from:
        return False, f"This quiz is not available yet. It opens on {quiz.available_from.strftime('%b %d, %Y at %H:%M')}."

    if now > quiz.available_to:
        return False, f"The availability window for this quiz closed on {quiz.available_to.strftime('%b %d, %Y at %H:%M')}."

    # Check attempt limit
    completed_attempts_count = QuizAttempt.objects.filter(
        quiz=quiz,
        student=user,
        status__in=[AttemptStatus.SUBMITTED, AttemptStatus.COMPLETED, AttemptStatus.EXPIRED],
    ).count()

    if completed_attempts_count >= quiz.max_attempts:
        return False, f"You have reached the maximum limit of {quiz.max_attempts} attempt(s) for this quiz."

    return True, "Eligible to start attempt."


def can_view_attempt_results(user, attempt: QuizAttempt) -> bool:
    """Check if the user is authorized to view the results of a specific quiz attempt."""
    if not user or not user.is_authenticated or not attempt:
        return False

    # 1. Administrator oversight
    if user.is_admin_role or user.is_superuser:
        return True

    # 2. Lecturer allocated to the course
    if user.is_lecturer_role:
        return CourseAllocation.objects.filter(
            course=attempt.quiz.course,
            lecturer=user,
            is_active=True,
        ).exists()

    # 3. Student who took the attempt
    if user.is_student_role:
        return attempt.student == user

    # 4. Parent linked to this student
    if user.is_parent_role:
        return ParentStudentRelationship.objects.filter(
            parent=user,
            student=attempt.student,
        ).exists()

    return False


def can_grade_attempt(user, attempt: QuizAttempt) -> bool:
    """Check if the user can evaluate short-answer responses and enter marks."""
    if not user or not user.is_authenticated or not attempt:
        return False

    if user.is_admin_role or user.is_superuser:
        return True

    if user.is_lecturer_role:
        return CourseAllocation.objects.filter(
            course=attempt.quiz.course,
            lecturer=user,
            is_active=True,
        ).exists()

    return False


def can_view_correct_answers(user, attempt: QuizAttempt) -> bool:
    """Check whether the user is permitted to see correct options, answer keys, and model answers."""
    if not user or not user.is_authenticated or not attempt:
        return False

    # Administrators and course lecturers always see full keys
    if user.is_admin_role or user.is_superuser:
        return True

    if user.is_lecturer_role:
        return CourseAllocation.objects.filter(
            course=attempt.quiz.course,
            lecturer=user,
            is_active=True,
        ).exists()

    # Students and Parents:
    # Must have view permission, attempt must be submitted/completed, and quiz must release answers
    if can_view_attempt_results(user, attempt):
        if not attempt.quiz.release_correct_answers:
            return False
        return attempt.status in [AttemptStatus.SUBMITTED, AttemptStatus.COMPLETED, AttemptStatus.EXPIRED]

    return False


def get_accessible_quizzes_queryset(user) -> QuerySet:
    """Return the scoped queryset of active quizzes the user has permission to view."""
    if not user or not user.is_authenticated:
        return Quiz.objects.none()

    base_qs = Quiz.objects.filter(is_active=True).select_related("course", "creator")

    if user.is_admin_role or user.is_superuser:
        return base_qs

    if user.is_lecturer_role:
        allocated_course_ids = CourseAllocation.objects.filter(
            lecturer=user,
            is_active=True,
        ).values_list("course_id", flat=True)
        return base_qs.filter(course_id__in=allocated_course_ids)

    if user.is_student_role:
        enrolled_course_ids = StudentEnrollment.objects.filter(
            student=user,
            is_active=True,
            status="ENROLLED",
        ).values_list("course_id", flat=True)
        return base_qs.filter(
            course_id__in=enrolled_course_ids,
            status=QuizStatus.PUBLISHED,
        )

    if user.is_parent_role:
        linked_student_ids = ParentStudentRelationship.objects.filter(
            parent=user
        ).values_list("student_id", flat=True)
        enrolled_course_ids = StudentEnrollment.objects.filter(
            student_id__in=linked_student_ids,
            is_active=True,
            status="ENROLLED",
        ).values_list("course_id", flat=True)
        return base_qs.filter(
            course_id__in=enrolled_course_ids,
            status=QuizStatus.PUBLISHED,
        )

    return Quiz.objects.none()
