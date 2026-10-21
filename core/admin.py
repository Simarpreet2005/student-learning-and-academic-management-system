from django.contrib import admin
from modeltranslation.admin import TranslationAdmin
from .models import Session, Semester, NewsAndEvents, Notification


class NewsAndEventsAdmin(TranslationAdmin):
    pass


class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "title", "notification_type", "is_read", "created_at")
    list_filter = ("notification_type", "is_read", "created_at")
    search_fields = ("user__username", "title", "message")


admin.site.register(Semester)
admin.site.register(Session)
admin.site.register(NewsAndEvents, NewsAndEventsAdmin)
admin.site.register(Notification, NotificationAdmin)
