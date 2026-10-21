"""Grading, scoring, and analytics service layer for Quizzes."""
from decimal import Decimal

from django.db import transaction
from django.db.models import Avg, Count, Max, Min
from django.utils import timezone

from .models import AttemptStatus, QuestionType, Quiz, QuizAttempt, StudentAnswer


class QuizGradingService:
    """Service handling deterministic automatic grading, score calculations, and grade compilation."""

    @classmethod
    def grade_objective_answer(cls, answer: StudentAnswer) -> None:
        """Evaluate a single objective student answer (Multiple Choice or True/False)."""
        question = answer.question

        if question.question_type in [QuestionType.MULTIPLE_CHOICE, QuestionType.TRUE_FALSE]:
            if answer.selected_option and answer.selected_option.is_correct:
                answer.marks_awarded = question.marks
                answer.is_correct = True
            else:
                answer.marks_awarded = Decimal("0.00")
                answer.is_correct = False
            answer.graded_at = timezone.now()
            answer.save(update_fields=["marks_awarded", "is_correct", "graded_at"])
        elif question.question_type == QuestionType.SHORT_ANSWER:
            # Leave short answers for lecturer manual evaluation unless already graded
            if answer.graded_at is None:
                answer.marks_awarded = Decimal("0.00")
                answer.is_correct = None
                answer.save(update_fields=["marks_awarded", "is_correct"])

    @classmethod
    @transaction.atomic
    def grade_attempt(
        cls,
        attempt: QuizAttempt,
        submitted_by_user=None,
        is_expired: bool = False,
    ) -> QuizAttempt:
        """Perform automatic grading across all answers, compute scores, and finalize attempt status."""
        # 1. Grade each individual objective answer
        answers = attempt.answers.select_related("question", "selected_option").all()
        for ans in answers:
            cls.grade_objective_answer(ans)

        # 2. Check if there are short answer questions pending manual review
        has_pending_manual = attempt.answers.filter(
            question__question_type=QuestionType.SHORT_ANSWER,
            graded_at__isnull=True,
        ).exists()

        now = timezone.now()
        if not attempt.submitted_at:
            attempt.submitted_at = now

        # Determine target status
        if is_expired:
            attempt.status = AttemptStatus.EXPIRED
        elif has_pending_manual:
            attempt.status = AttemptStatus.SUBMITTED
        else:
            attempt.status = AttemptStatus.COMPLETED
            attempt.graded_at = now

        # 3. Aggregate total earned marks and compute percentage
        total_earned = sum(
            (ans.marks_awarded for ans in attempt.answers.all()),
            Decimal("0.00"),
        )
        total_possible = attempt.quiz.computed_total_marks()
        if total_possible <= Decimal("0.00"):
            total_possible = attempt.quiz.total_marks

        attempt.score_obtained = total_earned
        attempt.total_marks = total_possible

        if total_possible > Decimal("0.00"):
            attempt.percentage = round((total_earned / total_possible) * Decimal("100.00"), 2)
        else:
            attempt.percentage = Decimal("0.00")

        attempt.is_passed = attempt.percentage >= attempt.quiz.pass_percentage
        attempt.save()
        return attempt

    @classmethod
    @transaction.atomic
    def finalize_manual_grading(
        cls,
        attempt: QuizAttempt,
        lecturer,
        overall_feedback: str = "",
    ) -> QuizAttempt:
        """Recompute scores after lecturer manual marking of short answers and mark completed."""
        total_earned = sum(
            (ans.marks_awarded for ans in attempt.answers.all()),
            Decimal("0.00"),
        )
        total_possible = attempt.quiz.computed_total_marks()
        if total_possible <= Decimal("0.00"):
            total_possible = attempt.quiz.total_marks

        attempt.score_obtained = total_earned
        attempt.total_marks = total_possible

        if total_possible > Decimal("0.00"):
            attempt.percentage = round((total_earned / total_possible) * Decimal("100.00"), 2)
        else:
            attempt.percentage = Decimal("0.00")

        attempt.is_passed = attempt.percentage >= attempt.quiz.pass_percentage
        attempt.status = AttemptStatus.COMPLETED
        attempt.graded_by = lecturer
        attempt.graded_at = timezone.now()
        if overall_feedback:
            attempt.feedback = overall_feedback

        attempt.save()
        return attempt

    @classmethod
    def get_quiz_statistics(cls, quiz: Quiz) -> dict:
        """Compute institutional course-level metrics and score distribution for a quiz."""
        completed_attempts = quiz.attempts.filter(
            status__in=[AttemptStatus.COMPLETED, AttemptStatus.SUBMITTED, AttemptStatus.EXPIRED]
        )

        total_attempts = completed_attempts.count()
        unique_students = completed_attempts.values("student").distinct().count()

        if total_attempts > 0:
            stats = completed_attempts.aggregate(
                avg_score=Avg("score_obtained"),
                avg_pct=Avg("percentage"),
                max_score=Max("score_obtained"),
                min_score=Min("score_obtained"),
            )
            passed_count = completed_attempts.filter(is_passed=True).count()
            failed_count = completed_attempts.filter(is_passed=False).count()
            pass_rate = round((Decimal(passed_count) / Decimal(total_attempts)) * Decimal("100.00"), 1)
        else:
            stats = {"avg_score": 0, "avg_pct": 0, "max_score": 0, "min_score": 0}
            passed_count = 0
            failed_count = 0
            pass_rate = Decimal("0.00")

        pending_manual = completed_attempts.filter(status=AttemptStatus.SUBMITTED).count()

        return {
            "total_attempts": total_attempts,
            "unique_students": unique_students,
            "average_score": round(stats["avg_score"] or 0, 2),
            "average_percentage": round(stats["avg_pct"] or 0, 2),
            "highest_score": round(stats["max_score"] or 0, 2),
            "lowest_score": round(stats["min_score"] or 0, 2),
            "passed_count": passed_count,
            "failed_count": failed_count,
            "pass_rate": pass_rate,
            "pending_manual_grading": pending_manual,
        }
