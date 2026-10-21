from django.urls import path
from . import views

urlpatterns = [
    path("course/<slug>/", views.assignment_list, name="assignment_list"),
    path("course/<slug>/create/", views.assignment_create, name="assignment_create"),
    path("<slug>/detail/", views.assignment_detail, name="assignment_detail"),
    path("<slug>/edit/", views.assignment_edit, name="assignment_edit"),
    path("<slug>/delete/", views.assignment_delete, name="assignment_delete"),
    path("<slug>/submit/", views.assignment_submit, name="assignment_submit"),
    path("<slug>/submissions/", views.submission_list, name="submission_list"),
    path("submissions/<int:pk>/grade/", views.submission_grade, name="submission_grade"),
    path("submissions/<int:pk>/download/", views.submission_download, name="submission_download"),
    path("my-assignments/", views.user_assignments, name="user_assignments"),
]
