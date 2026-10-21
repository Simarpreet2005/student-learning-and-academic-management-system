"""Role-based and object-level authorization helpers and mixins for Academic LMS.

Enforces strict server-side authorization boundaries across all four roles:
Admin, Lecturer, Student, and Parent.
"""
from functools import wraps
from typing import Sequence
from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from .models import Role, ParentStudentRelationship, User


def role_required(*allowed_roles: Sequence[str]):
    """Decorator ensuring the user is authenticated and belongs to an allowed role.

    If unauthenticated, redirects to login with the next parameter.
    If authenticated but unauthorized, raises PermissionDenied (HTTP 403).
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect(f"/accounts/login/?next={request.path}")

            user = request.user
            # Admins/Superusers bypass role check if ADMIN is in allowed_roles or explicitly allowed
            user_role = getattr(user, "role", None)
            if user.is_superuser or user.is_staff:
                if Role.ADMIN in allowed_roles:
                    return view_func(request, *args, **kwargs)

            if user_role not in allowed_roles:
                raise PermissionDenied("You do not have permission to access this resource.")

            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


def admin_required(view_func):
    """Decorator ensuring user is an Administrator or Staff."""
    return role_required(Role.ADMIN)(view_func)


def lecturer_required(view_func):
    """Decorator ensuring user is a Lecturer."""
    return role_required(Role.LECTURER)(view_func)


def student_required(view_func):
    """Decorator ensuring user is a Student."""
    return role_required(Role.STUDENT)(view_func)


def parent_required(view_func):
    """Decorator ensuring user is a Parent."""
    return role_required(Role.PARENT)(view_func)


class RoleRequiredMixin(AccessMixin):
    """CBV Mixin that verifies the user belongs to one of the specified allowed_roles."""

    allowed_roles: Sequence[str] = ()

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        user = request.user
        if (user.is_superuser or user.is_staff) and Role.ADMIN in self.allowed_roles:
            return super().dispatch(request, *args, **kwargs)

        if user.role not in self.allowed_roles:
            raise PermissionDenied("You do not have permission to access this resource.")

        return super().dispatch(request, *args, **kwargs)


class AdminRequiredMixin(RoleRequiredMixin):
    allowed_roles = (Role.ADMIN,)


class LecturerRequiredMixin(RoleRequiredMixin):
    allowed_roles = (Role.LECTURER,)


class StudentRequiredMixin(RoleRequiredMixin):
    allowed_roles = (Role.STUDENT,)


class ParentRequiredMixin(RoleRequiredMixin):
    allowed_roles = (Role.PARENT,)


# ==============================================================================
# Object-Level Authorization Helpers
# ==============================================================================

def can_view_student_data(request_user: User, student_user: User) -> bool:
    """Check if request_user has permission to view academic data of student_user."""
    if not request_user.is_authenticated or not student_user.is_authenticated:
        return False

    # Admins can view any student
    if request_user.is_admin_role:
        return True

    # Students can view their own data
    if request_user.id == student_user.id and student_user.is_student_role:
        return True

    # Parents can only view students who are explicitly linked to them
    if request_user.is_parent_role and student_user.is_student_role:
        return ParentStudentRelationship.objects.filter(
            parent=request_user,
            student=student_user,
        ).exists()

    return False


def can_edit_profile(request_user: User, target_user: User) -> bool:
    """Check if request_user has permission to edit profile of target_user.

    Rules:
    - User can edit their own basic profile fields.
    - Admins can manage user profiles.
    - Parents CANNOT edit linked students' records.
    - Students CANNOT edit anyone else's records.
    """
    if not request_user.is_authenticated:
        return False

    if request_user.is_admin_role:
        return True

    return request_user.id == target_user.id
