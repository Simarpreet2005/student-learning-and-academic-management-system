"""Root URL configuration for Academic LMS."""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

# Custom Admin Site Branding (Brown-and-Cream scholastic styling)
admin.site.site_header = "Academic LMS Administration"
admin.site.site_title = "Academic LMS Portal"
admin.site.index_title = "Institutional Governance & System Administration"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("enrollment/", include("apps.academics.urls")),
    path("assignments/", include("apps.assessments.urls")),
    path("courseware/", include("apps.courseware.urls")),
    path("quizzes/", include("apps.quizzes.urls")),
    path("planner/", include("apps.planner.urls")),
    path("", include("apps.core.urls")),
]

handler403 = "apps.accounts.views.access_denied_view"
handler500 = "apps.core.views.server_error_view"


# Serve media and static files in development mode
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
