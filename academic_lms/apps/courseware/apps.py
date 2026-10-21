from django.apps import AppConfig


class CoursewareConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.courseware"
    label = "courseware"
    verbose_name = "Courseware & Learning Materials"
