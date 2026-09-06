from django.contrib import admin

from .models import TakenCourse, Result


class ScoreAdmin(admin.ModelAdmin):
    list_display = [
        "student",
        "course",
        "assignment",
        "mid_exam",
        "quiz",
        "attendance",
        "final_exam",
        "total",
        "grade",
        "comment",
    ]


admin.site.register(TakenCourse, ScoreAdmin)
admin.site.register(Result)
