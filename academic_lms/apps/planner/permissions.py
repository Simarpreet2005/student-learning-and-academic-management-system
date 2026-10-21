"""Role-based authorization and object-level scoping helpers for the Workload Planner.

Enforces defensive security boundaries:
- Student: Access own workload overview, tasks, and configure study budget preferences.
- Lecturer: Access course-level workload cluster summaries strictly for allocated courses.
            Never allowed to access individual students' private study hour preferences.
- Parent: Strictly read-only observer access to workload summaries of explicitly linked students.
- Admin: Institutional oversight across all courses and student plans.
"""
from typing import Optional
from apps.accounts.models import ParentStudentRelationship, User
from apps.academics.models import Course, CourseAllocation


def can_view_student_workload(user: Optional[User], student_user: Optional[User]) -> bool:
    """Evaluate whether user can view the student's workload summary and task plan."""
    if not user or not user.is_authenticated or not student_user:
        return False

    # 1. Administrator oversight
    if getattr(user, "is_admin_role", False) or user.is_superuser:
        return True

    # 2. Student themselves
    if getattr(user, "is_student_role", False) and user.id == student_user.id:
        return True

    # 3. Parent: Must be explicitly linked via ParentStudentRelationship
    if getattr(user, "is_parent_role", False):
        return ParentStudentRelationship.objects.filter(
            parent=user,
            student=student_user,
        ).exists()

    return False


def can_manage_student_workload_preferences(user: Optional[User], student_user: Optional[User]) -> bool:
    """Evaluate whether user can configure the student's study budget preferences.

    Only the student themselves (or an administrator) can configure personal study hours.
    Parents and lecturers have zero mutation privileges.
    """
    if not user or not user.is_authenticated or not student_user:
        return False

    if getattr(user, "is_admin_role", False) or user.is_superuser:
        return True

    if getattr(user, "is_student_role", False) and user.id == student_user.id:
        return True

    return False


def can_view_course_workload(user: Optional[User], course: Optional[Course]) -> bool:
    """Evaluate whether user can view course-level deliverable clusters and submission stats.

    Only allocated lecturers and administrators can view course workload summaries.
    """
    if not user or not user.is_authenticated or not course:
        return False

    if getattr(user, "is_admin_role", False) or user.is_superuser:
        return True

    if getattr(user, "is_lecturer_role", False):
        return CourseAllocation.objects.filter(
            course=course,
            lecturer=user,
            is_active=True,
        ).exists()

    return False
