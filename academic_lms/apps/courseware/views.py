"""Views for Courseware & Digital Learning Materials."""
import mimetypes
import os
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404, HttpRequest, HttpResponse, FileResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.models import Role, ParentStudentRelationship
from apps.accounts.permissions import role_required
from apps.academics.models import Course, CourseAllocation
from .forms import LearningResourceForm, CourseModuleForm
from .models import LearningResource, ResourceType, ResourceStatus
from .permissions import (
    can_view_resource,
    can_manage_resource,
    get_accessible_resources_queryset,
)


@login_required
def resource_list_view(request: HttpRequest) -> HttpResponse:
    """List accessible learning resources with filtering, search, and pagination."""
    user = request.user
    base_qs = get_accessible_resources_queryset(user)

    # Search query
    query = request.GET.get("q", "").strip()
    if query:
        base_qs = base_qs.filter(
            Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(course__code__icontains=query)
            | Q(course__title__icontains=query)
        )

    # Filter by course
    selected_course = request.GET.get("course", "").strip()
    if selected_course:
        base_qs = base_qs.filter(course__code__iexact=selected_course)

    # Filter by resource type
    selected_type = request.GET.get("type", "").strip()
    if selected_type and selected_type in ResourceType.values:
        base_qs = base_qs.filter(resource_type=selected_type)

    # Filter by publication status (Allowed only for Admin & Lecturer)
    selected_status = request.GET.get("status", "").strip()
    if selected_status and (user.is_admin_role or user.is_lecturer_role):
        if selected_status in ResourceStatus.values:
            base_qs = base_qs.filter(status=selected_status)

    # Order by module, sort order, and recency
    base_qs = base_qs.order_by("-created_at")

    # Pagination
    paginator = Paginator(base_qs, 12)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # Determine selectable courses for filters
    if user.is_admin_role:
        available_courses = Course.objects.filter(is_active=True).order_by("code")
    elif user.is_lecturer_role:
        available_courses = Course.objects.filter(
            allocations__lecturer=user,
            allocations__is_active=True,
            is_active=True,
        ).distinct().order_by("code")
    elif user.is_student_role:
        available_courses = Course.objects.filter(
            enrollments__student=user,
            enrollments__is_active=True,
            enrollments__status="ENROLLED",
            is_active=True,
        ).distinct().order_by("code")
    elif user.is_parent_role:
        linked_student_ids = ParentStudentRelationship.objects.filter(
            parent=user
        ).values_list("student_id", flat=True)
        available_courses = Course.objects.filter(
            enrollments__student_id__in=linked_student_ids,
            enrollments__is_active=True,
            enrollments__status="ENROLLED",
            is_active=True,
        ).distinct().order_by("code")
    else:
        available_courses = Course.objects.none()

    can_create = user.is_admin_role or (user.is_lecturer_role and available_courses.exists())

    context = {
        "title": "Courseware & Learning Materials",
        "page_obj": page_obj,
        "is_paginated": page_obj.has_other_pages(),
        "query": query,
        "selected_course": selected_course,
        "selected_type": selected_type,
        "selected_status": selected_status,
        "available_courses": available_courses,
        "resource_types": ResourceType.choices,
        "status_choices": ResourceStatus.choices,
        "can_create": can_create,
    }
    return render(request, "courseware/resource_list.html", context)


@login_required
def resource_detail_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Detailed view for a specific learning material."""
    resource = get_object_or_404(
        LearningResource.objects.select_related("course", "module", "created_by"),
        pk=pk,
        is_active=True,
    )

    if not can_view_resource(request.user, resource):
        raise PermissionDenied("You do not have authorized permission to view this learning resource.")

    can_edit = can_manage_resource(request.user, resource=resource)

    context = {
        "title": f"{resource.title} | {resource.course.code}",
        "resource": resource,
        "can_edit": can_edit,
    }
    return render(request, "courseware/resource_detail.html", context)


@login_required
@role_required(Role.ADMIN, Role.LECTURER)
def resource_create_view(request: HttpRequest) -> HttpResponse:
    """Create a new digital learning resource."""
    user = request.user

    # Verify lecturer has allocated courses
    if user.is_lecturer_role:
        has_allocations = CourseAllocation.objects.filter(
            lecturer=user, is_active=True
        ).exists()
        if not has_allocations:
            messages.warning(
                request,
                "You are not currently allocated to any courses. Contact an administrator to allocate courses.",
            )
            return redirect("courseware:resource_list")

    if request.method == "POST":
        form = LearningResourceForm(request.POST, request.FILES, user=user)
        if form.is_valid():
            resource = form.save(commit=False)
            resource.created_by = user
            if not can_manage_resource(user, course=resource.course):
                raise PermissionDenied("You are not authorized to create resources for this course.")
            resource.save()
            messages.success(request, f"Learning resource '{resource.title}' has been successfully created.")
            return redirect("courseware:resource_detail", pk=resource.pk)
    else:
        initial = {}
        course_param = request.GET.get("course")
        if course_param:
            try:
                course_obj = Course.objects.get(code__iexact=course_param, is_active=True)
                initial["course"] = course_obj
            except Course.DoesNotExist:
                pass
        form = LearningResourceForm(user=user, initial=initial)

    context = {
        "title": "Upload Learning Resource",
        "form": form,
        "action": "Create",
    }
    return render(request, "courseware/resource_form.html", context)


@login_required
@role_required(Role.ADMIN, Role.LECTURER)
def resource_edit_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Edit an existing learning resource."""
    resource = get_object_or_404(
        LearningResource.objects.select_related("course"),
        pk=pk,
        is_active=True,
    )

    if not can_manage_resource(request.user, resource=resource):
        raise PermissionDenied("You are not authorized to edit this resource.")

    if request.method == "POST":
        form = LearningResourceForm(request.POST, request.FILES, instance=resource, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, f"Learning resource '{resource.title}' was successfully updated.")
            return redirect("courseware:resource_detail", pk=resource.pk)
    else:
        form = LearningResourceForm(instance=resource, user=request.user)

    context = {
        "title": f"Edit Resource — {resource.title}",
        "form": form,
        "resource": resource,
        "action": "Update",
    }
    return render(request, "courseware/resource_form.html", context)


@login_required
@role_required(Role.ADMIN, Role.LECTURER)
def resource_delete_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Soft deactivation for a learning resource."""
    resource = get_object_or_404(
        LearningResource.objects.select_related("course"),
        pk=pk,
        is_active=True,
    )

    if not can_manage_resource(request.user, resource=resource):
        raise PermissionDenied("You are not authorized to deactivate this resource.")

    if request.method == "POST":
        resource.is_active = False
        resource.save()
        messages.success(request, f"Learning resource '{resource.title}' has been deactivated.")
        return redirect("courseware:resource_list")

    context = {
        "title": f"Deactivate Resource — {resource.title}",
        "resource": resource,
    }
    return render(request, "courseware/resource_confirm_delete.html", context)


@login_required
def resource_download_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Securely stream an uploaded resource file after evaluating permissions.

    Never permits direct unauthenticated file retrieval or access to unauthorized/draft files.
    """
    resource = get_object_or_404(
        LearningResource.objects.select_related("course"),
        pk=pk,
        is_active=True,
    )

    if not can_view_resource(request.user, resource):
        raise PermissionDenied("You do not have permission to download this learning resource.")

    if not resource.file:
        raise Http404("This learning resource has no attached file.")

    try:
        file_handle = resource.file.open("rb")
    except (FileNotFoundError, OSError):
        raise Http404("The requested file could not be found in storage.")

    content_type, _ = mimetypes.guess_type(resource.original_filename or resource.file.name)
    download_filename = resource.original_filename or os.path.basename(resource.file.name)

    response = FileResponse(file_handle, content_type=content_type or "application/octet-stream")
    response["Content-Disposition"] = f'attachment; filename="{download_filename}"'
    return response


@login_required
@role_required(Role.ADMIN, Role.LECTURER)
def module_create_view(request: HttpRequest) -> HttpResponse:
    """Add a course module / topic grouping."""
    user = request.user
    if request.method == "POST":
        form = CourseModuleForm(request.POST, user=user)
        if form.is_valid():
            module = form.save()
            messages.success(request, f"Topic module '{module.title}' created for {module.course.code}.")
            return redirect("courseware:resource_create")
    else:
        form = CourseModuleForm(user=user)

    context = {
        "title": "Add Course Topic / Module",
        "form": form,
    }
    return render(request, "courseware/module_form.html", context)
