"""Permission evaluation helpers for Courseware and Learning Materials.

Strict server-side role and object-level boundaries:
- Admin: Unrestricted management across all resources.
- Lecturer: Manage (C/R/U/D) resources only for allocated courses (including drafts).
- Student: Read-only access to published resources for enrolled courses only.
- Parent: Read-only access to published resources for linked students' enrolled courses.
"""
from django.db.models import QuerySet
from apps.accounts.models import Role, ParentStudentRelationship
from apps.academics.models import CourseAllocation, StudentEnrollment
from .models import LearningResource, ResourceStatus


def can_view_resource(user, resource: LearningResource) -> bool:
    """Check if the given authenticated user has permission to view the learning resource."""
    if not user or not user.is_authenticated or not resource or not resource.is_active:
        return False

    # 1. Administrators have institutional access
    if user.is_admin_role:
        return True

    # 2. Lecturers: Must be allocated to the course (can view both draft and published)
    if user.is_lecturer_role:
        return CourseAllocation.objects.filter(
            course=resource.course,
            lecturer=user,
            is_active=True,
        ).exists()

    # 3. Students: Must be enrolled in the course AND resource must be PUBLISHED
    if user.is_student_role:
        if resource.status != ResourceStatus.PUBLISHED:
            return False
        return StudentEnrollment.objects.filter(
            course=resource.course,
            student=user,
            is_active=True,
            status="ENROLLED",
        ).exists()

    # 4. Parents: Must have at least one explicitly linked student enrolled AND resource must be PUBLISHED
    if user.is_parent_role:
        if resource.status != ResourceStatus.PUBLISHED:
            return False
        linked_student_ids = ParentStudentRelationship.objects.filter(
            parent=user
        ).values_list("student_id", flat=True)
        return StudentEnrollment.objects.filter(
            course=resource.course,
            student_id__in=linked_student_ids,
            is_active=True,
            status="ENROLLED",
        ).exists()

    return False


def can_manage_resource(user, resource: LearningResource = None, course=None) -> bool:
    """Check if the user is authorized to create, edit, publish, or deactivate the resource."""
    if not user or not user.is_authenticated:
        return False

    # 1. Administrator can manage all
    if user.is_admin_role:
        return True

    # 2. Lecturer can manage only if allocated to the target course
    if user.is_lecturer_role:
        target_course = course or (resource.course if resource else None)
        if not target_course:
            return False
        return CourseAllocation.objects.filter(
            course=target_course,
            lecturer=user,
            is_active=True,
        ).exists()

    # Students and Parents are strictly prohibited from management actions
    return False


def can_download_resource(user, resource: LearningResource) -> bool:
    """Check if the user can download the attached file."""
    if not resource or not resource.has_file:
        return False
    return can_view_resource(user, resource)


def get_accessible_resources_queryset(user) -> QuerySet:
    """Return the scoped queryset of active resources the user is permitted to view."""
    if not user or not user.is_authenticated:
        return LearningResource.objects.none()

    base_qs = LearningResource.objects.filter(is_active=True).select_related(
        "course", "module", "created_by"
    )

    if user.is_admin_role:
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
            status=ResourceStatus.PUBLISHED,
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
            status=ResourceStatus.PUBLISHED,
        )

    return LearningResource.objects.none()
