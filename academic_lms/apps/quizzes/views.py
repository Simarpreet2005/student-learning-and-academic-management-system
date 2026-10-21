"""Views for Quizzes, Question Management, Quiz Taking, and Grading Desk."""
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.models import ParentStudentRelationship, Role
from apps.accounts.permissions import role_required
from apps.academics.models import Course, CourseAllocation, StudentEnrollment
from .forms import (
    QuestionForm,
    QuestionOptionFormSet,
    QuizForm,
    ShortAnswerEvaluationForm,
)
from .models import (
    AttemptStatus,
    Question,
    QuestionOption,
    QuestionType,
    Quiz,
    QuizAttempt,
    QuizStatus,
    StudentAnswer,
)
from .permissions import (
    can_attempt_quiz,
    can_grade_attempt,
    can_manage_quiz,
    can_view_attempt_results,
    can_view_correct_answers,
    can_view_quiz,
    get_accessible_quizzes_queryset,
)
from .services import QuizGradingService


# ==============================================================================
# Quiz Catalog & Details Views
# ==============================================================================

@login_required
def quiz_list_view(request: HttpRequest) -> HttpResponse:
    """Display list of quizzes filtered by user role and course enrollments."""
    user = request.user
    base_qs = get_accessible_quizzes_queryset(user)

    # Search keyword
    query = request.GET.get("q", "").strip()
    if query:
        base_qs = base_qs.filter(
            Q(title__icontains=query)
            | Q(instructions__icontains=query)
            | Q(course__code__icontains=query)
            | Q(course__title__icontains=query)
        )

    # Filter by course
    selected_course = request.GET.get("course", "").strip()
    if selected_course:
        base_qs = base_qs.filter(course__code__iexact=selected_course)

    # Filter by publication status (Lecturer & Admin only)
    selected_status = request.GET.get("status", "").strip()
    if selected_status and (user.is_admin_role or user.is_lecturer_role):
        if selected_status in QuizStatus.values:
            base_qs = base_qs.filter(status=selected_status)

    # Filter by availability
    avail_filter = request.GET.get("avail", "").strip()
    now = timezone.now()
    if avail_filter == "open":
        base_qs = base_qs.filter(available_from__lte=now, available_to__gte=now)
    elif avail_filter == "upcoming":
        base_qs = base_qs.filter(available_from__gt=now)
    elif avail_filter == "concluded":
        base_qs = base_qs.filter(available_to__lt=now)

    base_qs = base_qs.order_by("-created_at")

    # Pagination
    paginator = Paginator(base_qs, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # Available courses for filter dropdown
    if user.is_admin_role or user.is_superuser:
        available_courses = Course.objects.filter(is_active=True).order_by("code")
    elif user.is_lecturer_role:
        alloc_ids = CourseAllocation.objects.filter(lecturer=user, is_active=True).values_list("course_id", flat=True)
        available_courses = Course.objects.filter(id__in=alloc_ids, is_active=True).order_by("code")
    elif user.is_student_role:
        enr_ids = StudentEnrollment.objects.filter(student=user, is_active=True, status="ENROLLED").values_list("course_id", flat=True)
        available_courses = Course.objects.filter(id__in=enr_ids, is_active=True).order_by("code")
    elif user.is_parent_role:
        linked_ids = ParentStudentRelationship.objects.filter(parent=user).values_list("student_id", flat=True)
        enr_ids = StudentEnrollment.objects.filter(student_id__in=linked_ids, is_active=True, status="ENROLLED").values_list("course_id", flat=True)
        available_courses = Course.objects.filter(id__in=enr_ids, is_active=True).order_by("code")
    else:
        available_courses = Course.objects.none()

    can_create = user.is_admin_role or (user.is_lecturer_role and available_courses.exists())

    context = {
        "page_obj": page_obj,
        "query": query,
        "selected_course": selected_course,
        "selected_status": selected_status,
        "avail_filter": avail_filter,
        "available_courses": available_courses,
        "can_create": can_create,
        "QuizStatus": QuizStatus,
    }
    return render(request, "quizzes/quiz_list.html", context)


@login_required
def quiz_detail_view(request: HttpRequest, pk: int) -> HttpResponse:
    """View quiz overview, instructions, attempt history, and starting options."""
    quiz = get_object_or_404(Quiz.objects.select_related("course", "creator"), pk=pk, is_active=True)
    user = request.user

    if not can_view_quiz(user, quiz):
        raise PermissionDenied("You do not have permission to view this quiz.")

    can_manage = can_manage_quiz(user, quiz)
    can_attempt, attempt_reason = can_attempt_quiz(user, quiz)

    # Student personal attempt history
    student_attempts = []
    active_in_progress_attempt = None
    if user.is_student_role:
        student_attempts = quiz.attempts.filter(student=user).order_by("-attempt_number")
        active_in_progress_attempt = student_attempts.filter(status=AttemptStatus.IN_PROGRESS).first()
        if active_in_progress_attempt and active_in_progress_attempt.is_time_expired():
            # Auto-grade and finalize expired attempt
            QuizGradingService.grade_attempt(active_in_progress_attempt, is_expired=True)
            active_in_progress_attempt = None

    # Parent view: linked student attempts
    parent_student_attempts = []
    if user.is_parent_role:
        linked_student_ids = ParentStudentRelationship.objects.filter(parent=user).values_list("student_id", flat=True)
        parent_student_attempts = quiz.attempts.filter(
            student_id__in=linked_student_ids
        ).select_related("student").order_by("-submitted_at")

    # Lecturer / Admin stats
    stats = {}
    if can_manage:
        stats = QuizGradingService.get_quiz_statistics(quiz)

    context = {
        "quiz": quiz,
        "can_manage": can_manage,
        "can_attempt": can_attempt,
        "attempt_reason": attempt_reason,
        "student_attempts": student_attempts,
        "active_attempt": active_in_progress_attempt,
        "parent_student_attempts": parent_student_attempts,
        "stats": stats,
        "questions_count": quiz.questions.count(),
        "total_possible_marks": quiz.computed_total_marks(),
    }
    return render(request, "quizzes/quiz_detail.html", context)


# ==============================================================================
# Lecturer Quiz Authoring & Editing
# ==============================================================================

@login_required
@role_required(Role.ADMIN, Role.LECTURER)
def quiz_create_view(request: HttpRequest) -> HttpResponse:
    """Create a new quiz (Admin or allocated Lecturer)."""
    user = request.user

    if request.method == "POST":
        form = QuizForm(request.POST, user=user)
        if form.is_valid():
            quiz = form.save(commit=False)
            quiz.creator = user
            quiz.save()
            messages.success(
                request,
                f"Quiz '{quiz.title}' created successfully! Now add questions below.",
            )
            return redirect("quizzes:question_manage", pk=quiz.pk)
    else:
        initial_data = {
            "available_from": timezone.now().strftime("%Y-%m-%dT%H:%M"),
            "available_to": (timezone.now() + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M"),
            "duration_minutes": 30,
            "pass_percentage": Decimal("50.00"),
            "max_attempts": 1,
            "status": QuizStatus.DRAFT,
        }
        form = QuizForm(user=user, initial=initial_data)

    return render(request, "quizzes/quiz_form.html", {"form": form, "action": "Create"})


@login_required
@role_required(Role.ADMIN, Role.LECTURER)
def quiz_edit_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Edit quiz settings and availability windows."""
    quiz = get_object_or_404(Quiz, pk=pk, is_active=True)
    if not can_manage_quiz(request.user, quiz):
        raise PermissionDenied("You are not authorized to edit this quiz.")

    if request.method == "POST":
        form = QuizForm(request.POST, instance=quiz, user=request.user)
        if form.is_valid():
            saved_quiz = form.save()
            saved_quiz.sync_total_marks()
            messages.success(request, f"Quiz '{saved_quiz.title}' updated successfully.")
            return redirect("quizzes:quiz_detail", pk=saved_quiz.pk)
    else:
        form = QuizForm(instance=quiz, user=request.user)

    return render(
        request,
        "quizzes/quiz_form.html",
        {"form": form, "quiz": quiz, "action": "Edit"},
    )


@login_required
@role_required(Role.ADMIN, Role.LECTURER)
def quiz_delete_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Soft-deactivate a quiz."""
    quiz = get_object_or_404(Quiz, pk=pk, is_active=True)
    if not can_manage_quiz(request.user, quiz):
        raise PermissionDenied("You are not authorized to delete this quiz.")

    if request.method == "POST":
        quiz.is_active = False
        quiz.save(update_fields=["is_active", "updated_at"])
        messages.success(request, f"Quiz '{quiz.title}' has been successfully archived/deleted.")
        return redirect("quizzes:quiz_list")

    return render(request, "quizzes/quiz_confirm_delete.html", {"quiz": quiz})


# ==============================================================================
# Question & Option Authoring Views
# ==============================================================================

@login_required
@role_required(Role.ADMIN, Role.LECTURER)
def question_manage_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Manage the list of questions belonging to a quiz, with ordering and mark balance."""
    quiz = get_object_or_404(Quiz.objects.select_related("course"), pk=pk, is_active=True)
    if not can_manage_quiz(request.user, quiz):
        raise PermissionDenied("You are not authorized to manage questions for this quiz.")

    questions = quiz.questions.prefetch_related("options").all().order_by("order", "id")
    computed_marks = quiz.computed_total_marks()

    if request.method == "POST" and "sync_marks" in request.POST:
        quiz.sync_total_marks()
        messages.success(request, f"Total marks synchronized to {quiz.total_marks}.")
        return redirect("quizzes:question_manage", pk=quiz.pk)

    context = {
        "quiz": quiz,
        "questions": questions,
        "computed_marks": computed_marks,
        "marks_mismatch": abs(quiz.total_marks - computed_marks) > Decimal("0.01"),
    }
    return render(request, "quizzes/question_manage.html", context)


@login_required
@role_required(Role.ADMIN, Role.LECTURER)
def question_create_view(request: HttpRequest, quiz_pk: int) -> HttpResponse:
    """Add a new question with options to a quiz."""
    quiz = get_object_or_404(Quiz, pk=quiz_pk, is_active=True)
    if not can_manage_quiz(request.user, quiz):
        raise PermissionDenied("You are not authorized to add questions to this quiz.")

    next_order = (quiz.questions.count() or 0) + 1

    if request.method == "POST":
        form = QuestionForm(request.POST)
        question = Question(quiz=quiz)
        formset = QuestionOptionFormSet(request.POST, instance=question)

        q_type = request.POST.get("question_type")

        if form.is_valid():
            question = form.save(commit=False)
            question.quiz = quiz

            if q_type == QuestionType.SHORT_ANSWER:
                question.save()
                quiz.sync_total_marks()
                messages.success(request, "Short-answer question created successfully.")
                return redirect("quizzes:question_manage", pk=quiz.pk)
            else:
                formset = QuestionOptionFormSet(request.POST, instance=question)
                if formset.is_valid():
                    question.save()
                    formset.save()
                    quiz.sync_total_marks()
                    messages.success(request, "Question and options created successfully.")
                    return redirect("quizzes:question_manage", pk=quiz.pk)
                else:
                    messages.error(request, "Please correct the option errors below.")
    else:
        form = QuestionForm(initial={"order": next_order, "marks": Decimal("1.00"), "question_type": QuestionType.MULTIPLE_CHOICE})
        question = Question(quiz=quiz, question_type=QuestionType.MULTIPLE_CHOICE)
        formset = QuestionOptionFormSet(instance=question)

    return render(
        request,
        "quizzes/question_form.html",
        {
            "quiz": quiz,
            "form": form,
            "formset": formset,
            "action": "Add",
            "QuestionType": QuestionType,
        },
    )


@login_required
@role_required(Role.ADMIN, Role.LECTURER)
def question_edit_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Edit an existing question and its options."""
    question = get_object_or_404(Question.objects.select_related("quiz"), pk=pk)
    quiz = question.quiz
    if not can_manage_quiz(request.user, quiz):
        raise PermissionDenied("You are not authorized to edit this question.")

    if request.method == "POST":
        form = QuestionForm(request.POST, instance=question)
        formset = QuestionOptionFormSet(request.POST, instance=question)
        q_type = request.POST.get("question_type", question.question_type)

        if form.is_valid():
            question = form.save()

            if q_type == QuestionType.SHORT_ANSWER:
                # Delete any stale options if type switched to short answer
                question.options.all().delete()
                quiz.sync_total_marks()
                messages.success(request, "Question updated successfully.")
                return redirect("quizzes:question_manage", pk=quiz.pk)
            else:
                if formset.is_valid():
                    formset.save()
                    quiz.sync_total_marks()
                    messages.success(request, "Question and options updated successfully.")
                    return redirect("quizzes:question_manage", pk=quiz.pk)
                else:
                    messages.error(request, "Please correct the option errors below.")
    else:
        form = QuestionForm(instance=question)
        formset = QuestionOptionFormSet(instance=question)

    return render(
        request,
        "quizzes/question_form.html",
        {
            "quiz": quiz,
            "question": question,
            "form": form,
            "formset": formset,
            "action": "Edit",
            "QuestionType": QuestionType,
        },
    )


@login_required
@role_required(Role.ADMIN, Role.LECTURER)
def question_delete_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete a question from a quiz."""
    question = get_object_or_404(Question.objects.select_related("quiz"), pk=pk)
    quiz = question.quiz
    if not can_manage_quiz(request.user, quiz):
        raise PermissionDenied("You are not authorized to delete this question.")

    if request.method == "POST":
        question.delete()
        quiz.sync_total_marks()
        messages.success(request, "Question removed successfully.")
        return redirect("quizzes:question_manage", pk=quiz.pk)

    return render(
        request,
        "quizzes/question_confirm_delete.html",
        {"quiz": quiz, "question": question},
    )


# ==============================================================================
# Student Quiz-Taking & Server-Side Time Enforcement
# ==============================================================================

@login_required
@role_required(Role.STUDENT)
def quiz_start_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Initialize a new attempt or resume an active in-progress attempt."""
    quiz = get_object_or_404(Quiz, pk=pk, is_active=True)
    user = request.user

    can_attempt, message_reason = can_attempt_quiz(user, quiz)
    if not can_attempt:
        messages.error(request, message_reason)
        return redirect("quizzes:quiz_detail", pk=quiz.pk)

    with transaction.atomic():
        # Check for existing in-progress attempt
        active_attempt = (
            QuizAttempt.objects.select_for_update()
            .filter(quiz=quiz, student=user, status=AttemptStatus.IN_PROGRESS)
            .first()
        )
        if active_attempt:
            if active_attempt.is_time_expired():
                # Finalize expired attempt
                QuizGradingService.grade_attempt(active_attempt, is_expired=True)
                messages.warning(
                    request,
                    "Your previous attempt time has elapsed. The attempt has been finalized.",
                )
                return redirect("quizzes:quiz_result", attempt_pk=active_attempt.pk)
            return redirect("quizzes:quiz_take", quiz_pk=quiz.pk, attempt_pk=active_attempt.pk)

        # Determine attempt number
        prev_attempts_count = QuizAttempt.objects.filter(quiz=quiz, student=user).count()
        next_attempt_number = prev_attempts_count + 1

        if next_attempt_number > quiz.max_attempts:
            messages.error(
                request,
                f"You have reached the maximum allowed limit of {quiz.max_attempts} attempt(s).",
            )
            return redirect("quizzes:quiz_detail", pk=quiz.pk)

        # Create new attempt
        attempt = QuizAttempt(
            quiz=quiz,
            student=user,
            attempt_number=next_attempt_number,
            status=AttemptStatus.IN_PROGRESS,
            started_at=timezone.now(),
        )
        attempt.initialize_question_ordering()
        attempt.save()

        # Seed empty answers for each question
        for q in quiz.questions.all():
            StudentAnswer.objects.create(attempt=attempt, question=q)

    messages.info(
        request,
        f"Attempt #{attempt.attempt_number} started! You have {quiz.duration_minutes} minutes.",
    )
    return redirect("quizzes:quiz_take", quiz_pk=quiz.pk, attempt_pk=attempt.pk)


@login_required
@role_required(Role.STUDENT)
def quiz_take_view(request: HttpRequest, quiz_pk: int, attempt_pk: int) -> HttpResponse:
    """The interactive quiz-taking desk with live timer and server-side deadline enforcement."""
    quiz = get_object_or_404(Quiz, pk=quiz_pk, is_active=True)
    attempt = get_object_or_404(
        QuizAttempt.objects.select_related("quiz", "student"),
        pk=attempt_pk,
        quiz=quiz,
        student=request.user,
    )

    # 1. Enforce attempt state: If already submitted or expired, forbid changes
    if attempt.status in [AttemptStatus.SUBMITTED, AttemptStatus.COMPLETED, AttemptStatus.EXPIRED]:
        messages.info(request, "This quiz attempt has already been finalized and cannot be modified.")
        return redirect("quizzes:quiz_result", attempt_pk=attempt.pk)

    # Handle submission or draft save
    if request.method == "POST":
        action = request.POST.get("action", "save")

        with transaction.atomic():
            # Refresh lock on attempt
            attempt = QuizAttempt.objects.select_for_update().get(pk=attempt.pk)

            if attempt.status in [AttemptStatus.SUBMITTED, AttemptStatus.COMPLETED, AttemptStatus.EXPIRED]:
                messages.info(request, "This quiz attempt has already been finalized.")
                return redirect("quizzes:quiz_result", attempt_pk=attempt.pk)

            is_expired = attempt.is_time_expired()

            # Save student responses submitted in POST
            questions = quiz.questions.all()
            for q in questions:
                answer, _ = StudentAnswer.objects.get_or_create(attempt=attempt, question=q)

                if q.question_type in [QuestionType.MULTIPLE_CHOICE, QuestionType.TRUE_FALSE]:
                    selected_opt_id = request.POST.get(f"question_{q.id}")
                    if selected_opt_id and selected_opt_id.isdigit():
                        opt = QuestionOption.objects.filter(id=int(selected_opt_id), question=q).first()
                        answer.selected_option = opt
                    else:
                        answer.selected_option = None
                    answer.save(update_fields=["selected_option"])
                elif q.question_type == QuestionType.SHORT_ANSWER:
                    text_resp = request.POST.get(f"question_{q.id}", "").strip()
                    answer.text_response = text_resp
                    answer.save(update_fields=["text_response"])

            if is_expired:
                QuizGradingService.grade_attempt(attempt, is_expired=True)
                messages.warning(
                    request,
                    "The allotted time for this quiz has expired. Your responses have been automatically submitted and scored.",
                )
                return redirect("quizzes:quiz_result", attempt_pk=attempt.pk)
            elif action == "submit":
                QuizGradingService.grade_attempt(attempt, is_expired=False)
                messages.success(
                    request,
                    "Quiz successfully submitted! Your answers have been recorded.",
                )
                return redirect("quizzes:quiz_result", attempt_pk=attempt.pk)
            else:
                messages.success(request, "Your answers have been saved. Continue working.")

    # GET request: server-side time enforcement
    if attempt.is_time_expired():
        QuizGradingService.grade_attempt(attempt, is_expired=True)
        messages.warning(
            request,
            "The allotted time for this quiz has expired. Your responses have been automatically submitted and scored.",
        )
        return redirect("quizzes:quiz_result", attempt_pk=attempt.pk)

    # GET request: load question list in frozen attempt order
    question_id_order = attempt.question_order or list(
        quiz.questions.order_by("order", "id").values_list("id", flat=True)
    )

    questions_dict = {
        q.id: q for q in quiz.questions.prefetch_related("options").filter(id__in=question_id_order)
    }
    ordered_questions = [questions_dict[qid] for qid in question_id_order if qid in questions_dict]

    # Existing answers mapped by question_id
    answers_map = {ans.question_id: ans for ans in attempt.answers.all()}

    # Attach ordered options and current answer to each question item
    question_cards = []
    for idx, q in enumerate(ordered_questions, start=1):
        opt_ids = attempt.option_order.get(str(q.id))
        if opt_ids:
            opts_dict = {opt.id: opt for opt in q.options.all()}
            ordered_options = [opts_dict[oid] for oid in opt_ids if oid in opts_dict]
        else:
            ordered_options = list(q.options.all().order_by("order", "id"))

        ans = answers_map.get(q.id)
        question_cards.append({
            "number": idx,
            "question": q,
            "options": ordered_options,
            "answer": ans,
        })

    remaining_seconds = attempt.get_remaining_seconds()

    context = {
        "quiz": quiz,
        "attempt": attempt,
        "question_cards": question_cards,
        "remaining_seconds": remaining_seconds,
        "effective_deadline": attempt.effective_deadline,
        "QuestionType": QuestionType,
    }
    return render(request, "quizzes/quiz_take.html", context)


# ==============================================================================
# Results, Feedback, and Grading Desk
# ==============================================================================

@login_required
def quiz_result_view(request: HttpRequest, attempt_pk: int) -> HttpResponse:
    """Inspect student score, breakdown, feedback, and permitted answer keys."""
    attempt = get_object_or_404(
        QuizAttempt.objects.select_related("quiz", "student", "quiz__course", "graded_by"),
        pk=attempt_pk,
    )
    user = request.user

    if not can_view_attempt_results(user, attempt):
        raise PermissionDenied("You do not have permission to view results for this attempt.")

    quiz = attempt.quiz
    show_keys = can_view_correct_answers(user, attempt)
    can_grade = can_grade_attempt(user, attempt)

    # Fetch answers with questions
    answers = (
        attempt.answers.select_related("question", "selected_option")
        .prefetch_related("question__options")
        .order_by("question__order", "question__id")
    )

    context = {
        "quiz": quiz,
        "attempt": attempt,
        "answers": answers,
        "show_keys": show_keys,
        "can_grade": can_grade,
        "is_parent_view": user.is_parent_role,
        "QuestionType": QuestionType,
        "AttemptStatus": AttemptStatus,
    }
    return render(request, "quizzes/quiz_result.html", context)


@login_required
@role_required(Role.ADMIN, Role.LECTURER)
def attempt_review_view(request: HttpRequest, attempt_pk: int) -> HttpResponse:
    """Lecturer manual grading desk for short-answer questions and qualitative feedback."""
    attempt = get_object_or_404(
        QuizAttempt.objects.select_related("quiz", "student", "quiz__course"),
        pk=attempt_pk,
    )
    if not can_grade_attempt(request.user, attempt):
        raise PermissionDenied("You are not authorized to grade this quiz attempt.")

    quiz = attempt.quiz
    answers = (
        attempt.answers.select_related("question", "selected_option")
        .prefetch_related("question__options")
        .order_by("question__order", "question__id")
    )

    if request.method == "POST":
        overall_feedback = request.POST.get("overall_feedback", "").strip()

        with transaction.atomic():
            has_errors = False
            for ans in answers:
                if ans.question.question_type == QuestionType.SHORT_ANSWER:
                    raw_marks = request.POST.get(f"marks_{ans.id}")
                    comment = request.POST.get(f"comment_{ans.id}", "").strip()

                    try:
                        marks_val = Decimal(raw_marks)
                        if marks_val < Decimal("0.00") or marks_val > ans.question.marks:
                            messages.error(
                                request,
                                f"Marks for Q{ans.question.order} must be between 0 and {ans.question.marks}.",
                            )
                            has_errors = True
                            break
                        ans.marks_awarded = marks_val
                        ans.lecturer_comment = comment
                        ans.is_correct = marks_val >= (ans.question.marks * Decimal("0.5"))
                        ans.graded_by = request.user
                        ans.graded_at = timezone.now()
                        ans.save()
                    except (ValueError, TypeError):
                        messages.error(request, f"Invalid marks entered for Q{ans.question.order}.")
                        has_errors = True
                        break

            if not has_errors:
                QuizGradingService.finalize_manual_grading(
                    attempt=attempt,
                    lecturer=request.user,
                    overall_feedback=overall_feedback,
                )
                messages.success(
                    request,
                    f"Grading finalized successfully for {attempt.student.get_full_name}.",
                )
                return redirect("quizzes:quiz_result", attempt_pk=attempt.pk)

    context = {
        "quiz": quiz,
        "attempt": attempt,
        "answers": answers,
        "QuestionType": QuestionType,
    }
    return render(request, "quizzes/attempt_review.html", context)


@login_required
@role_required(Role.ADMIN, Role.LECTURER)
def course_quiz_results_view(request: HttpRequest, quiz_pk: int) -> HttpResponse:
    """Course-level gradebook overview showing all student attempts for a quiz."""
    quiz = get_object_or_404(Quiz.objects.select_related("course"), pk=quiz_pk, is_active=True)
    if not can_manage_quiz(request.user, quiz):
        raise PermissionDenied("You are not authorized to view results for this course.")

    # All student enrollments for this course
    enrolled_students = StudentEnrollment.objects.filter(
        course=quiz.course,
        is_active=True,
        status="ENROLLED",
    ).select_related("student", "student__student_profile").order_by("student__last_name", "student__first_name")

    # Fetch attempts
    attempts = (
        quiz.attempts.select_related("student", "graded_by")
        .order_by("student__last_name", "student__first_name", "-attempt_number")
    )

    # Map attempts by student_id
    attempts_by_student = {}
    for att in attempts:
        attempts_by_student.setdefault(att.student_id, []).append(att)

    roster = []
    for enr in enrolled_students:
        std = enr.student
        std_attempts = attempts_by_student.get(std.id, [])
        best_score = max((a.score_obtained for a in std_attempts), default=None)
        best_percentage = max((a.percentage for a in std_attempts), default=None)
        has_passed = any(a.is_passed for a in std_attempts)

        roster.append({
            "student": std,
            "enrollment": enr,
            "attempts": std_attempts,
            "attempts_count": len(std_attempts),
            "best_score": best_score,
            "best_percentage": best_percentage,
            "has_passed": has_passed,
        })

    stats = QuizGradingService.get_quiz_statistics(quiz)

    context = {
        "quiz": quiz,
        "roster": roster,
        "stats": stats,
        "total_enrolled": enrolled_students.count(),
        "AttemptStatus": AttemptStatus,
    }
    return render(request, "quizzes/course_results.html", context)
