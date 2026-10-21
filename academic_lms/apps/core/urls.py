from django.urls import path
from .views import academic_calendar_view, dev_showcase_view, index_view

app_name = "core"

urlpatterns = [
    path("", index_view, name="index"),
    path("calendar/", academic_calendar_view, name="calendar"),
    path("dev-showcase/", dev_showcase_view, name="dev_showcase"),
]
