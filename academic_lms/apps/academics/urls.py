"""Student enrollment routes."""
from django.urls import path
from .views import enrollment_catalog_view

app_name = "academics"

urlpatterns = [
    path("", enrollment_catalog_view, name="enrollment_catalog"),
]
