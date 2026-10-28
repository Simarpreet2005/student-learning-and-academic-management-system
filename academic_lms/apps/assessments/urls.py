"""Assignment routes."""
from django.urls import path
from . import views

app_name = "assessments"

urlpatterns = [
    path("", views.assignment_list_view, name="list"),
    path("create/", views.assignment_create_view, name="create"),
    path("<int:pk>/", views.assignment_detail_view, name="detail"),
    path("<int:pk>/edit/", views.assignment_edit_view, name="edit"),
    path("submissions/<int:submission_id>/grade/", views.assignment_grade_view, name="grade"),
    path("submissions/<int:submission_id>/file/", views.assignment_submission_download_view, name="download_submission"),
]
