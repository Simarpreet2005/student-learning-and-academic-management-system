"""Django Admin registrations for Quizzes, Questions, Options, and Attempts."""
from django.contrib import admin
from .models import (
    Quiz,
    Question,
    QuestionOption,
    QuizAttempt,
    StudentAnswer,
)


class QuestionOptionInline(admin.TabularInline):
    model = QuestionOption
    extra = 2
    fields = ("text", "is_correct", "order")


class QuestionInline(admin.StackedInline):
    model = Question
    extra = 0
    fields = ("text", "question_type", "marks", "order", "model_answer")


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "course",
        "creator",
        "duration_minutes",
        "total_marks",
        "pass_percentage",
        "max_attempts",
        "status",
        "is_active",
        "available_from",
        "available_to",
    )
    list_filter = ("status", "is_active", "course", "shuffle_questions", "release_correct_answers")
    search_fields = ("title", "instructions", "course__code", "course__title", "creator__username")
    readonly_fields = ("created_at", "updated_at")
    inlines = [QuestionInline]


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("__str__", "quiz", "question_type", "marks", "order")
    list_filter = ("question_type", "quiz__course")
    search_fields = ("text", "model_answer", "quiz__title")
    inlines = [QuestionOptionInline]


class StudentAnswerInline(admin.TabularInline):
    model = StudentAnswer
    extra = 0
    readonly_fields = ("question", "selected_option", "text_response", "marks_awarded", "is_correct", "graded_by", "graded_at")
    can_delete = False


@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = (
        "student",
        "quiz",
        "attempt_number",
        "status",
        "score_obtained",
        "total_marks",
        "percentage",
        "is_passed",
        "started_at",
        "submitted_at",
    )
    list_filter = ("status", "is_passed", "quiz__course")
    search_fields = ("student__username", "student__first_name", "student__last_name", "quiz__title")
    readonly_fields = (
        "started_at",
        "submitted_at",
        "graded_at",
        "score_obtained",
        "total_marks",
        "percentage",
        "is_passed",
        "question_order",
        "option_order",
    )
    inlines = [StudentAnswerInline]


@admin.register(StudentAnswer)
class StudentAnswerAdmin(admin.ModelAdmin):
    list_display = ("attempt", "question", "selected_option", "marks_awarded", "is_correct", "graded_at")
    list_filter = ("is_correct", "question__question_type")
    search_fields = ("attempt__student__username", "question__text", "text_response")
