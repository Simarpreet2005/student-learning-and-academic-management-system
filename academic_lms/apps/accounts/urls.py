"""URL patterns for accounts app."""
from django.urls import path
from .views import (
    login_view,
    logout_view,
    profile_view,
    profile_edit_view,
    student_detail_view,
    admin_dashboard_view,
    lecturer_dashboard_view,
    student_dashboard_view,
    parent_dashboard_view,
    admin_relationship_list_view,
    admin_relationship_create_view,
    admin_relationship_delete_view,
    CustomPasswordChangeView,
    CustomPasswordResetView,
    CustomPasswordResetDoneView,
    CustomPasswordResetConfirmView,
    CustomPasswordResetCompleteView,
    access_denied_view,
)

app_name = "accounts"

urlpatterns = [
    # Authentication routes
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("access-denied/", access_denied_view, name="access_denied"),

    # Role-Specific Dashboards
    path("dashboard/admin/", admin_dashboard_view, name="admin_dashboard"),
    path("dashboard/lecturer/", lecturer_dashboard_view, name="lecturer_dashboard"),
    path("dashboard/student/", student_dashboard_view, name="student_dashboard"),
    path("dashboard/parent/", parent_dashboard_view, name="parent_dashboard"),

    # User Profile & Authorized Inspection
    path("profile/", profile_view, name="profile"),
    path("profile/edit/", profile_edit_view, name="profile_edit"),
    path("students/<int:student_id>/", student_detail_view, name="student_detail"),

    # Admin: Parent–Student Linkage Management
    path("admin/relationships/", admin_relationship_list_view, name="admin_relationship_list"),
    path("admin/relationships/add/", admin_relationship_create_view, name="admin_relationship_create"),
    path("admin/relationships/<int:pk>/delete/", admin_relationship_delete_view, name="admin_relationship_delete"),

    # Password Management
    path("password/change/", CustomPasswordChangeView.as_view(), name="password_change"),
    path("password/reset/", CustomPasswordResetView.as_view(), name="password_reset"),
    path("password/reset/done/", CustomPasswordResetDoneView.as_view(), name="password_reset_done"),
    path("password/reset/<uidb64>/<token>/", CustomPasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("password/reset/complete/", CustomPasswordResetCompleteView.as_view(), name="password_reset_complete"),
]
