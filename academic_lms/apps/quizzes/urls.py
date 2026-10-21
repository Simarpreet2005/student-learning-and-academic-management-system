"""URL configuration for Quizzes and Assessments."""
from django.urls import path
from . import views

app_name = "quizzes"

urlpatterns = [
    # Catalog & Details
    path("", views.quiz_list_view, name="quiz_list"),
    path("create/", views.quiz_create_view, name="quiz_create"),
    path("<int:pk>/", views.quiz_detail_view, name="quiz_detail"),
    path("<int:pk>/edit/", views.quiz_edit_view, name="quiz_edit"),
    path("<int:pk>/delete/", views.quiz_delete_view, name="quiz_delete"),

    # Question & Option Authoring
    path("<int:pk>/questions/", views.question_manage_view, name="question_manage"),
    path("<int:quiz_pk>/questions/add/", views.question_create_view, name="question_create"),
    path("questions/<int:pk>/edit/", views.question_edit_view, name="question_edit"),
    path("questions/<int:pk>/delete/", views.question_delete_view, name="question_delete"),

    # Student Quiz Taking
    path("<int:pk>/start/", views.quiz_start_view, name="quiz_start"),
    path("<int:quiz_pk>/attempt/<int:attempt_pk>/", views.quiz_take_view, name="quiz_take"),

    # Results & Evaluation
    path("attempt/<int:attempt_pk>/results/", views.quiz_result_view, name="quiz_result"),
    path("attempt/<int:attempt_pk>/grade/", views.attempt_review_view, name="attempt_review"),
    path("<int:quiz_pk>/course-results/", views.course_quiz_results_view, name="course_quiz_results"),
]
