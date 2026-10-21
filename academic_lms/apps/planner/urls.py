"""URL routing patterns for the Rule-Based Smart Academic Workload Planner."""
from django.urls import path
from . import views

app_name = "planner"

urlpatterns = [
    path("", views.student_workload_dashboard_view, name="dashboard"),
    path("preferences/", views.study_budget_preferences_view, name="preferences"),
    path("course/<int:course_id>/", views.course_workload_view, name="course_workload"),
    path("student/<int:student_id>/", views.parent_student_workload_view, name="student_workload"),
]
