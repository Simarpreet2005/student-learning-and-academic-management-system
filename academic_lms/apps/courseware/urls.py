"""URL configuration for Courseware and Digital Learning Materials."""
from django.urls import path
from . import views

app_name = "courseware"

urlpatterns = [
    path("", views.resource_list_view, name="resource_list"),
    path("create/", views.resource_create_view, name="resource_create"),
    path("<int:pk>/", views.resource_detail_view, name="resource_detail"),
    path("<int:pk>/edit/", views.resource_edit_view, name="resource_edit"),
    path("<int:pk>/delete/", views.resource_delete_view, name="resource_delete"),
    path("<int:pk>/download/", views.resource_download_view, name="resource_download"),
    path("modules/create/", views.module_create_view, name="module_create"),
]
