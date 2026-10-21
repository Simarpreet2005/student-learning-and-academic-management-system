"""Comprehensive automated test suite for Quizzes, Grading, and Results.

Tests:
- Quiz model constraints, availability windows, and question validation.
- Course allocation and student enrollment permissions.
- Availability windows and attempt limits enforcement.
- Server-side time-limit enforcement and expiration handling.
- Correct-answer confidentiality before permitted release.
- Automatic grading calculations and lecturer manual grading.
- Prevention of edits after submission.
- Student and parent result isolation.
- Unauthorized direct requests.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role, ParentStudentRelationship, StudentProfile, LecturerProfile, ParentProfile
from apps.academics.models import (
    Department,
    AcademicProgram,
    AcademicYear,
    Semester,
    Course,
    CourseAllocation,
    StudentEnrollment,
    EnrollmentStatus,
)
from apps.quizzes.models import (
    Quiz,
    QuizStatus,
    Question,
    QuestionType,
    QuestionOption,
    QuizAttempt,
    AttemptStatus,
    StudentAnswer,
)
from apps.quizzes.permissions import (
    can_view_quiz,
    can_manage_quiz,
    can_attempt_quiz,
    can_view_attempt_results,
    can_grade_attempt,
    can_view_correct_answers,
)
from apps.quizzes.services import QuizGradingService

User = get_user_model()


class BaseQuizTestCase(TestCase):
    """Base setup fixture providing department, courses, allocations, and 4-role users."""

    def setUp(self):
        super().setUp()
        self.now = timezone.now()

        # Department & Program
        self.department = Department.objects.create(name="Computer Science", code="CS")
        self.program = AcademicProgram.objects.create(
            department=self.department, name="B.Sc. Software Engineering", code="SE"
        )

        # Academic Calendar
        self.acad_year = AcademicYear.objects.create(
            name="2026/2027",
            start_date=(self.now - timedelta(days=30)).date(),
            end_date=(self.now + timedelta(days=300)).date(),
            is_current=True,
        )
        self.semester = Semester.objects.create(
            academic_year=self.acad_year,
            name="Fall 2026",
            start_date=(self.now - timedelta(days=15)).date(),
            end_date=(self.now + timedelta(days=120)).date(),
            is_active=True,
        )

        # Courses
        self.course_a = Course.objects.create(code="CS301", title="Database Systems", credits=3, department=self.department)
        self.course_b = Course.objects.create(code="CS302", title="Algorithms", credits=4, department=self.department)

        # Users
        self.admin_user = User.objects.create_superuser(
            username="admin_user", email="admin@example.com", password="password123", role=Role.ADMIN
        )
        self.lecturer_a = User.objects.create_user(
            username="lecturer_a", email="lec_a@example.com", password="password123", role=Role.LECTURER, first_name="Alan", last_name="Turing"
        )
        LecturerProfile.objects.create(user=self.lecturer_a, employee_id="LEC001", department="Computer Science")

        self.lecturer_b = User.objects.create_user(
            username="lecturer_b", email="lec_b@example.com", password="password123", role=Role.LECTURER, first_name="Grace", last_name="Hopper"
        )
        LecturerProfile.objects.create(user=self.lecturer_b, employee_id="LEC002", department="Computer Science")

        self.student_1 = User.objects.create_user(
            username="student_1", email="std1@example.com", password="password123", role=Role.STUDENT, first_name="Ada", last_name="Lovelace"
        )
        StudentProfile.objects.create(user=self.student_1, student_id="STD001", program="SE")

        self.student_2 = User.objects.create_user(
            username="student_2", email="std2@example.com", password="password123", role=Role.STUDENT, first_name="Charles", last_name="Babbage"
        )
        StudentProfile.objects.create(user=self.student_2, student_id="STD002", program="SE")

        self.parent_1 = User.objects.create_user(
            username="parent_1", email="par1@example.com", password="password123", role=Role.PARENT, first_name="Lord", last_name="Byron"
        )
        ParentProfile.objects.create(user=self.parent_1)

        self.parent_unlinked = User.objects.create_user(
            username="parent_unlinked", email="par_un@example.com", password="password123", role=Role.PARENT, first_name="John", last_name="Doe"
        )
        ParentProfile.objects.create(user=self.parent_unlinked)

        # Parent-Student Link: parent_1 linked to student_1
        ParentStudentRelationship.objects.create(
            parent=self.parent_1, student=self.student_1, relationship_type="FATHER"
        )

        # Lecturer Course Allocation: lecturer_a allocated to course_a
        CourseAllocation.objects.create(
            course=self.course_a, lecturer=self.lecturer_a, semester=self.semester, is_active=True
        )

        # Student Enrollment: student_1 enrolled in course_a; student_2 enrolled in course_b
        StudentEnrollment.objects.create(
            course=self.course_a, student=self.student_1, semester=self.semester, status=EnrollmentStatus.ENROLLED, is_active=True
        )
        StudentEnrollment.objects.create(
            course=self.course_b, student=self.student_2, semester=self.semester, status=EnrollmentStatus.ENROLLED, is_active=True
        )

        # Clients
        self.admin_client = Client()
        self.admin_client.force_login(self.admin_user)

        self.lecturer_a_client = Client()
        self.lecturer_a_client.force_login(self.lecturer_a)

        self.lecturer_b_client = Client()
        self.lecturer_b_client.force_login(self.lecturer_b)

        self.student_1_client = Client()
        self.student_1_client.force_login(self.student_1)

        self.student_2_client = Client()
        self.student_2_client.force_login(self.student_2)

        self.parent_1_client = Client()
        self.parent_1_client.force_login(self.parent_1)

        self.parent_unlinked_client = Client()
        self.parent_unlinked_client.force_login(self.parent_unlinked)


class QuizModelAndValidationTests(BaseQuizTestCase):
    """Test model constraints, validation logic, and totals consistency."""

    def test_availability_window_validation(self):
        """Available_to cannot be chronologically before available_from."""
        quiz = Quiz(
            course=self.course_a,
            creator=self.lecturer_a,
            title="Invalid Window Quiz",
            available_from=self.now + timedelta(days=5),
            available_to=self.now + timedelta(days=2),
            duration_minutes=30,
        )
        with self.assertRaises(ValidationError) as ctx:
            quiz.clean()
        self.assertIn("available_to", ctx.exception.message_dict)

    def test_cannot_publish_empty_quiz(self):
        """A quiz cannot be marked PUBLISHED if it contains zero questions."""
        quiz = Quiz.objects.create(
            course=self.course_a,
            creator=self.lecturer_a,
            title="Empty Quiz",
            available_from=self.now - timedelta(hours=1),
            available_to=self.now + timedelta(days=1),
            duration_minutes=30,
            status=QuizStatus.DRAFT,
        )
        quiz.status = QuizStatus.PUBLISHED
        with self.assertRaises(ValidationError) as ctx:
            quiz.clean()
        self.assertIn("status", ctx.exception.message_dict)

    def test_question_option_validation_mcq(self):
        """MCQ must have at least 2 options and exactly 1 correct option."""
        quiz = Quiz.objects.create(
            course=self.course_a,
            creator=self.lecturer_a,
            title="MCQ Validation Quiz",
            available_from=self.now - timedelta(hours=1),
            available_to=self.now + timedelta(days=1),
            duration_minutes=30,
            status=QuizStatus.DRAFT,
        )
        q = Question.objects.create(
            quiz=quiz,
            text="What is SQL?",
            question_type=QuestionType.MULTIPLE_CHOICE,
            marks=Decimal("2.00"),
            order=1,
        )

        # Less than 2 options raises ValidationError
        QuestionOption.objects.create(question=q, text="Option 1", is_correct=True)
        with self.assertRaises(ValidationError):
            q.validate_options()

        # 2 options but 0 correct raises ValidationError
        opt2 = QuestionOption.objects.create(question=q, text="Option 2", is_correct=False)
        QuestionOption.objects.filter(pk=q.options.first().pk).update(is_correct=False)
        with self.assertRaises(ValidationError):
            q.validate_options()

        # 2 options with 1 correct passes
        QuestionOption.objects.filter(pk=opt2.pk).update(is_correct=True)
        q.validate_options()  # Should not raise

    def test_question_option_validation_true_false(self):
        """True/False question must have exactly 2 options and exactly 1 correct option."""
        quiz = Quiz.objects.create(
            course=self.course_a,
            creator=self.lecturer_a,
            title="TF Validation Quiz",
            available_from=self.now - timedelta(hours=1),
            available_to=self.now + timedelta(days=1),
            duration_minutes=30,
            status=QuizStatus.DRAFT,
        )
        q = Question.objects.create(
            quiz=quiz,
            text="Django is a Python framework.",
            question_type=QuestionType.TRUE_FALSE,
            marks=Decimal("1.00"),
            order=1,
        )
        QuestionOption.objects.create(question=q, text="True", is_correct=True)
        QuestionOption.objects.create(question=q, text="False", is_correct=False)
        q.validate_options()  # Should not raise

        # 3 options raises ValidationError
        QuestionOption.objects.create(question=q, text="Maybe", is_correct=False)
        with self.assertRaises(ValidationError):
            q.validate_options()

    def test_sync_total_marks(self):
        """Quiz total_marks correctly synchronizes with the sum of question marks."""
        quiz = Quiz.objects.create(
            course=self.course_a,
            creator=self.lecturer_a,
            title="Marks Sync Quiz",
            available_from=self.now - timedelta(hours=1),
            available_to=self.now + timedelta(days=1),
            duration_minutes=30,
            status=QuizStatus.DRAFT,
            total_marks=Decimal("0.00"),
        )
        Question.objects.create(quiz=quiz, text="Q1", question_type=QuestionType.SHORT_ANSWER, marks=Decimal("3.50"), order=1)
        Question.objects.create(quiz=quiz, text="Q2", question_type=QuestionType.SHORT_ANSWER, marks=Decimal("6.50"), order=2)

        quiz.sync_total_marks()
        quiz.refresh_from_db()
        self.assertEqual(quiz.total_marks, Decimal("10.00"))


class QuizPermissionAndScopingTests(BaseQuizTestCase):
    """Test RBAC and object-level permission enforcement."""

    def setUp(self):
        super().setUp()
        self.quiz = Quiz.objects.create(
            course=self.course_a,
            creator=self.lecturer_a,
            title="Database Intro Quiz",
            available_from=self.now - timedelta(hours=1),
            available_to=self.now + timedelta(days=2),
            duration_minutes=30,
            status=QuizStatus.PUBLISHED,
            total_marks=Decimal("5.00"),
        )

    def test_can_manage_quiz(self):
        """Only Admin and allocated lecturer can manage the quiz."""
        self.assertTrue(can_manage_quiz(self.admin_user, self.quiz))
        self.assertTrue(can_manage_quiz(self.lecturer_a, self.quiz))
        # Lecturer B is not allocated to Course A
        self.assertFalse(can_manage_quiz(self.lecturer_b, self.quiz))
        # Student and Parent cannot manage
        self.assertFalse(can_manage_quiz(self.student_1, self.quiz))
        self.assertFalse(can_manage_quiz(self.parent_1, self.quiz))

    def test_can_view_quiz(self):
        """Enrolled student can view published quiz; un-enrolled student cannot."""
        # Student 1 is enrolled in Course A
        self.assertTrue(can_view_quiz(self.student_1, self.quiz))
        # Student 2 is enrolled in Course B, not Course A
        self.assertFalse(can_view_quiz(self.student_2, self.quiz))
        # Parent 1 is linked to Student 1
        self.assertTrue(can_view_quiz(self.parent_1, self.quiz))
        # Unlinked parent cannot view
        self.assertFalse(can_view_quiz(self.parent_unlinked, self.quiz))

    def test_draft_quiz_hidden_from_students_and_parents(self):
        """Draft quizzes must be completely inaccessible to students and parents."""
        self.quiz.status = QuizStatus.DRAFT
        self.quiz.save()

        self.assertFalse(can_view_quiz(self.student_1, self.quiz))
        self.assertFalse(can_view_quiz(self.parent_1, self.quiz))
        # But allocated lecturer and admin can view drafts
        self.assertTrue(can_view_quiz(self.lecturer_a, self.quiz))
        self.assertTrue(can_view_quiz(self.admin_user, self.quiz))

    def test_attempt_eligibility_and_limits(self):
        """Student eligibility checks enforce enrollment, windows, and max attempts."""
        can_att, _ = can_attempt_quiz(self.student_1, self.quiz)
        self.assertTrue(can_att)

        # Un-enrolled student cannot attempt
        can_att, reason = can_attempt_quiz(self.student_2, self.quiz)
        self.assertFalse(can_att)
        self.assertIn("enrolled", reason.lower())

        # Max attempts limit: set max_attempts to 1 and create completed attempt
        self.quiz.max_attempts = 1
        self.quiz.save()

        QuizAttempt.objects.create(
            quiz=self.quiz,
            student=self.student_1,
            attempt_number=1,
            status=AttemptStatus.COMPLETED,
            submitted_at=self.now,
        )

        can_att, reason = can_attempt_quiz(self.student_1, self.quiz)
        self.assertFalse(can_att)
        self.assertIn("maximum limit", reason.lower())


class QuizTakingAndServerTimerTests(BaseQuizTestCase):
    """Test quiz taking, question shuffling, and server-side timer enforcement."""

    def setUp(self):
        super().setUp()
        self.quiz = Quiz.objects.create(
            course=self.course_a,
            creator=self.lecturer_a,
            title="SQL Queries Quiz",
            available_from=self.now - timedelta(hours=1),
            available_to=self.now + timedelta(days=2),
            duration_minutes=20,
            status=QuizStatus.PUBLISHED,
            total_marks=Decimal("10.00"),
            max_attempts=2,
            shuffle_questions=True,
            shuffle_options=True,
        )
        self.q1 = Question.objects.create(
            quiz=self.quiz, text="Which SQL keyword is used to retrieve data?", question_type=QuestionType.MULTIPLE_CHOICE, marks=Decimal("5.00"), order=1
        )
        self.opt1_correct = QuestionOption.objects.create(question=self.q1, text="SELECT", is_correct=True, order=1)
        self.opt1_wrong = QuestionOption.objects.create(question=self.q1, text="GET", is_correct=False, order=2)

        self.q2 = Question.objects.create(
            quiz=self.quiz, text="Primary keys cannot be NULL.", question_type=QuestionType.TRUE_FALSE, marks=Decimal("5.00"), order=2
        )
        self.opt2_correct = QuestionOption.objects.create(question=self.q2, text="True", is_correct=True, order=1)
        self.opt2_wrong = QuestionOption.objects.create(question=self.q2, text="False", is_correct=False, order=2)

    def test_start_quiz_creates_attempt_with_frozen_order(self):
        """Starting a quiz freezes question and option orders per attempt."""
        response = self.student_1_client.post(reverse("quizzes:quiz_start", kwargs={"pk": self.quiz.pk}))
        self.assertEqual(response.status_code, 302)

        attempt = QuizAttempt.objects.filter(quiz=self.quiz, student=self.student_1).first()
        self.assertIsNotNone(attempt)
        self.assertEqual(attempt.status, AttemptStatus.IN_PROGRESS)
        self.assertIn(self.q1.id, attempt.question_order)
        self.assertIn(self.q2.id, attempt.question_order)
        self.assertEqual(len(attempt.question_order), 2)

    def test_resume_in_progress_attempt(self):
        """Starting a quiz when an in-progress attempt exists resumes it instead of creating duplicates."""
        attempt = QuizAttempt.objects.create(
            quiz=self.quiz,
            student=self.student_1,
            attempt_number=1,
            status=AttemptStatus.IN_PROGRESS,
            started_at=self.now,
        )
        attempt.initialize_question_ordering()
        attempt.save()

        response = self.student_1_client.post(reverse("quizzes:quiz_start", kwargs={"pk": self.quiz.pk}))
        self.assertRedirects(response, reverse("quizzes:quiz_take", kwargs={"quiz_pk": self.quiz.pk, "attempt_pk": attempt.pk}))
        self.assertEqual(QuizAttempt.objects.filter(quiz=self.quiz, student=self.student_1).count(), 1)

    def test_server_side_timer_expiration_on_submission(self):
        """Submissions received after the server-side time limit are marked EXPIRED and auto-graded."""
        # Create an attempt started 30 minutes ago for a 20-minute quiz
        attempt = QuizAttempt.objects.create(
            quiz=self.quiz,
            student=self.student_1,
            attempt_number=1,
            status=AttemptStatus.IN_PROGRESS,
            started_at=self.now - timedelta(minutes=30),
        )
        attempt.initialize_question_ordering()
        attempt.save()

        # Submit answers
        post_data = {
            "action": "submit",
            f"question_{self.q1.id}": self.opt1_correct.id,
            f"question_{self.q2.id}": self.opt2_correct.id,
        }
        response = self.student_1_client.post(
            reverse("quizzes:quiz_take", kwargs={"quiz_pk": self.quiz.pk, "attempt_pk": attempt.pk}),
            data=post_data,
        )
        self.assertRedirects(response, reverse("quizzes:quiz_result", kwargs={"attempt_pk": attempt.pk}))

        attempt.refresh_from_db()
        self.assertEqual(attempt.status, AttemptStatus.EXPIRED)
        # Even though expired, answers submitted are evaluated
        self.assertEqual(attempt.score_obtained, Decimal("10.00"))

    def test_cannot_modify_submitted_attempt(self):
        """Once an attempt is SUBMITTED, COMPLETED, or EXPIRED, it cannot be modified."""
        attempt = QuizAttempt.objects.create(
            quiz=self.quiz,
            student=self.student_1,
            attempt_number=1,
            status=AttemptStatus.COMPLETED,
            started_at=self.now - timedelta(minutes=10),
            submitted_at=self.now,
            score_obtained=Decimal("5.00"),
        )
        # Attempt to post to take view
        response = self.student_1_client.post(
            reverse("quizzes:quiz_take", kwargs={"quiz_pk": self.quiz.pk, "attempt_pk": attempt.pk}),
            data={"action": "submit"},
        )
        self.assertRedirects(response, reverse("quizzes:quiz_result", kwargs={"attempt_pk": attempt.pk}))


class QuizGradingAndResultsTests(BaseQuizTestCase):
    """Test objective auto-grading, short-answer manual grading, and answer key confidentiality."""

    def setUp(self):
        super().setUp()
        self.quiz = Quiz.objects.create(
            course=self.course_a,
            creator=self.lecturer_a,
            title="Mixed Assessment Quiz",
            available_from=self.now - timedelta(hours=1),
            available_to=self.now + timedelta(days=2),
            duration_minutes=30,
            status=QuizStatus.PUBLISHED,
            total_marks=Decimal("15.00"),
            pass_percentage=Decimal("60.00"),
            release_correct_answers=False,  # Answer key confidential
        )
        # 1. Multiple Choice (5 pts)
        self.q_mcq = Question.objects.create(
            quiz=self.quiz, text="What does DDL stand for?", question_type=QuestionType.MULTIPLE_CHOICE, marks=Decimal("5.00"), order=1
        )
        self.opt_ddl_correct = QuestionOption.objects.create(question=self.q_mcq, text="Data Definition Language", is_correct=True, order=1)
        self.opt_ddl_wrong = QuestionOption.objects.create(question=self.q_mcq, text="Data Direct Link", is_correct=False, order=2)

        # 2. True / False (5 pts)
        self.q_tf = Question.objects.create(
            quiz=self.quiz, text="SQLite supports concurrency via row-level locks.", question_type=QuestionType.TRUE_FALSE, marks=Decimal("5.00"), order=2
        )
        self.opt_tf_true = QuestionOption.objects.create(question=self.q_tf, text="True", is_correct=False, order=1)
        self.opt_tf_false = QuestionOption.objects.create(question=self.q_tf, text="False", is_correct=True, order=2)

        # 3. Short Answer (5 pts)
        self.q_sa = Question.objects.create(
            quiz=self.quiz,
            text="Explain the concept of database normalization in 2 sentences.",
            question_type=QuestionType.SHORT_ANSWER,
            marks=Decimal("5.00"),
            order=3,
            model_answer="Normalization organizes data to reduce redundancy and improve data integrity (1NF, 2NF, 3NF).",
        )

    def test_objective_auto_grading_and_short_answer_pending(self):
        """MCQ and TF are graded automatically; Short Answer puts attempt in SUBMITTED status."""
        attempt = QuizAttempt.objects.create(
            quiz=self.quiz,
            student=self.student_1,
            attempt_number=1,
            status=AttemptStatus.IN_PROGRESS,
            started_at=self.now,
        )
        # Ans 1: Correct MCQ
        StudentAnswer.objects.create(attempt=attempt, question=self.q_mcq, selected_option=self.opt_ddl_correct)
        # Ans 2: Incorrect TF
        StudentAnswer.objects.create(attempt=attempt, question=self.q_tf, selected_option=self.opt_tf_true)
        # Ans 3: Short Answer
        StudentAnswer.objects.create(attempt=attempt, question=self.q_sa, text_response="It organizes tables to eliminate redundancy.")

        QuizGradingService.grade_attempt(attempt)
        attempt.refresh_from_db()

        # Status must be SUBMITTED because short answer is pending manual review
        self.assertEqual(attempt.status, AttemptStatus.SUBMITTED)
        # Score earned so far: 5 (from MCQ) + 0 (from TF) = 5
        self.assertEqual(attempt.score_obtained, Decimal("5.00"))
        self.assertEqual(attempt.total_marks, Decimal("15.00"))
        self.assertEqual(attempt.percentage, Decimal("33.33"))

    def test_lecturer_manual_grading_desk(self):
        """Allocated lecturer can evaluate short answer, award marks, and finalize attempt."""
        attempt = QuizAttempt.objects.create(
            quiz=self.quiz,
            student=self.student_1,
            attempt_number=1,
            status=AttemptStatus.SUBMITTED,
            started_at=self.now,
            submitted_at=self.now,
            score_obtained=Decimal("5.00"),
            total_marks=Decimal("15.00"),
        )
        # Create objective answers: 5.00 for MCQ, 0.00 for TF
        StudentAnswer.objects.create(
            attempt=attempt, question=self.q_mcq, selected_option=self.opt_ddl_correct, marks_awarded=Decimal("5.00"), is_correct=True
        )
        StudentAnswer.objects.create(
            attempt=attempt, question=self.q_tf, selected_option=self.opt_tf_true, marks_awarded=Decimal("0.00"), is_correct=False
        )
        sa_ans = StudentAnswer.objects.create(
            attempt=attempt, question=self.q_sa, text_response="Reduces data duplication and preserves dependencies."
        )

        grade_url = reverse("quizzes:attempt_review", kwargs={"attempt_pk": attempt.pk})
        post_data = {
            f"marks_{sa_ans.id}": "4.50",
            f"comment_{sa_ans.id}": "Solid definition, good mention of dependencies.",
            "overall_feedback": "Good attempt overall. Review SQLite locking mechanisms.",
        }
        response = self.lecturer_a_client.post(grade_url, data=post_data)
        self.assertRedirects(response, reverse("quizzes:quiz_result", kwargs={"attempt_pk": attempt.pk}))

        attempt.refresh_from_db()
        sa_ans.refresh_from_db()

        self.assertEqual(attempt.status, AttemptStatus.COMPLETED)
        self.assertEqual(sa_ans.marks_awarded, Decimal("4.50"))
        # 5.00 (from previous) + 4.50 = 9.50 / 15.00 = 63.33%
        self.assertEqual(attempt.score_obtained, Decimal("9.50"))
        self.assertEqual(attempt.percentage, Decimal("63.33"))
        self.assertTrue(attempt.is_passed)  # 63.33% >= 60.00%
        self.assertEqual(attempt.graded_by, self.lecturer_a)
        self.assertIn("Solid definition", sa_ans.lecturer_comment)

    def test_manual_grading_exceeding_max_marks_rejected(self):
        """Entering marks greater than question marks is rejected."""
        attempt = QuizAttempt.objects.create(
            quiz=self.quiz,
            student=self.student_1,
            attempt_number=1,
            status=AttemptStatus.SUBMITTED,
            started_at=self.now,
            submitted_at=self.now,
        )
        sa_ans = StudentAnswer.objects.create(attempt=attempt, question=self.q_sa, text_response="Test answer")

        grade_url = reverse("quizzes:attempt_review", kwargs={"attempt_pk": attempt.pk})
        # Try awarding 10 marks for a 5 mark question
        post_data = {f"marks_{sa_ans.id}": "10.00"}
        response = self.lecturer_a_client.post(grade_url, data=post_data)
        self.assertEqual(response.status_code, 200)

        attempt.refresh_from_db()
        self.assertEqual(attempt.status, AttemptStatus.SUBMITTED)  # Not completed

    def test_unallocated_lecturer_cannot_grade(self):
        """Lecturer B (not allocated to Course A) cannot grade the attempt."""
        attempt = QuizAttempt.objects.create(
            quiz=self.quiz,
            student=self.student_1,
            attempt_number=1,
            status=AttemptStatus.SUBMITTED,
            started_at=self.now,
            submitted_at=self.now,
        )
        grade_url = reverse("quizzes:attempt_review", kwargs={"attempt_pk": attempt.pk})
        response = self.lecturer_b_client.get(grade_url)
        self.assertEqual(response.status_code, 403)

    def test_answer_key_confidentiality(self):
        """When release_correct_answers is False, students and parents cannot view correct keys."""
        attempt = QuizAttempt.objects.create(
            quiz=self.quiz,
            student=self.student_1,
            attempt_number=1,
            status=AttemptStatus.COMPLETED,
            started_at=self.now,
            submitted_at=self.now,
            score_obtained=Decimal("10.00"),
            total_marks=Decimal("15.00"),
        )
        self.assertFalse(can_view_correct_answers(self.student_1, attempt))
        self.assertFalse(can_view_correct_answers(self.parent_1, attempt))
        # But lecturer and admin always see correct keys
        self.assertTrue(can_view_correct_answers(self.lecturer_a, attempt))
        self.assertTrue(can_view_correct_answers(self.admin_user, attempt))

        # When released, student and linked parent can view keys
        self.quiz.release_correct_answers = True
        self.quiz.save()
        self.assertTrue(can_view_correct_answers(self.student_1, attempt))
        self.assertTrue(can_view_correct_answers(self.parent_1, attempt))


class QuizResultIsolationAndDirectAccessTests(BaseQuizTestCase):
    """Test result isolation between students and parent-child linkage security."""

    def setUp(self):
        super().setUp()
        self.quiz = Quiz.objects.create(
            course=self.course_a,
            creator=self.lecturer_a,
            title="Privacy Verification Quiz",
            available_from=self.now - timedelta(hours=1),
            available_to=self.now + timedelta(days=2),
            duration_minutes=30,
            status=QuizStatus.PUBLISHED,
            total_marks=Decimal("10.00"),
        )
        self.attempt_student_1 = QuizAttempt.objects.create(
            quiz=self.quiz,
            student=self.student_1,
            attempt_number=1,
            status=AttemptStatus.COMPLETED,
            started_at=self.now,
            submitted_at=self.now,
            score_obtained=Decimal("8.00"),
            total_marks=Decimal("10.00"),
        )

    def test_student_cannot_view_another_students_result(self):
        """Student 2 cannot view Student 1's quiz results."""
        result_url = reverse("quizzes:quiz_result", kwargs={"attempt_pk": self.attempt_student_1.pk})
        response = self.student_2_client.get(result_url)
        self.assertEqual(response.status_code, 403)

    def test_unlinked_parent_cannot_view_result(self):
        """Unlinked parent receives 403 when trying to access Student 1's results."""
        result_url = reverse("quizzes:quiz_result", kwargs={"attempt_pk": self.attempt_student_1.pk})
        response = self.parent_unlinked_client.get(result_url)
        self.assertEqual(response.status_code, 403)

    def test_linked_parent_can_view_result(self):
        """Parent 1 (explicitly linked to Student 1) can view Student 1's results."""
        result_url = reverse("quizzes:quiz_result", kwargs={"attempt_pk": self.attempt_student_1.pk})
        response = self.parent_1_client.get(result_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Parent Portal Observation")
        self.assertContains(response, self.student_1.get_full_name)

    def test_anonymous_access_redirects_to_login(self):
        """Unauthenticated user is redirected to login."""
        anon_client = Client()
        result_url = reverse("quizzes:quiz_result", kwargs={"attempt_pk": self.attempt_student_1.pk})
        response = anon_client.get(result_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)


class QuizCRUDAndQuestionAuthoringViewTests(BaseQuizTestCase):
    """Integration tests for Quiz and Question authoring views."""

    def test_quiz_list_view_and_filtering(self):
        """Quiz list view filters by keyword, course, and availability."""
        q1 = Quiz.objects.create(
            course=self.course_a,
            creator=self.lecturer_a,
            title="Database Intro",
            available_from=self.now - timedelta(hours=1),
            available_to=self.now + timedelta(days=2),
            duration_minutes=30,
            status=QuizStatus.PUBLISHED,
        )
        q2 = Quiz.objects.create(
            course=self.course_a,
            creator=self.lecturer_a,
            title="Advanced SQL",
            available_from=self.now + timedelta(days=10),
            available_to=self.now + timedelta(days=20),
            duration_minutes=45,
            status=QuizStatus.PUBLISHED,
        )

        response = self.student_1_client.get(reverse("quizzes:quiz_list"), {"q": "Intro"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Database Intro")
        self.assertNotContains(response, "Advanced SQL")

        # Availability filter: open
        response = self.student_1_client.get(reverse("quizzes:quiz_list"), {"avail": "open"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Database Intro")
        self.assertNotContains(response, "Advanced SQL")

    def test_lecturer_create_quiz_view(self):
        """Allocated lecturer can create a quiz and is redirected to question management."""
        create_url = reverse("quizzes:quiz_create")
        post_data = {
            "course": self.course_a.id,
            "title": "New Web Architecture Quiz",
            "instructions": "Follow university guidelines.",
            "available_from": (self.now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
            "available_to": (self.now + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M"),
            "duration_minutes": 40,
            "total_marks": "10.00",
            "pass_percentage": "50.00",
            "max_attempts": 1,
            "status": QuizStatus.DRAFT,
        }
        response = self.lecturer_a_client.post(create_url, data=post_data)
        self.assertEqual(response.status_code, 302)

        created = Quiz.objects.filter(title="New Web Architecture Quiz").first()
        self.assertIsNotNone(created)
        self.assertEqual(created.creator, self.lecturer_a)
        self.assertRedirects(response, reverse("quizzes:question_manage", kwargs={"pk": created.pk}))

    def test_student_cannot_access_quiz_create_or_edit(self):
        """Students receive 403 Forbidden when attempting to access quiz creation or editing."""
        create_url = reverse("quizzes:quiz_create")
        response = self.student_1_client.get(create_url)
        self.assertEqual(response.status_code, 403)

        quiz = Quiz.objects.create(
            course=self.course_a,
            creator=self.lecturer_a,
            title="Edit Quiz Test",
            available_from=self.now,
            available_to=self.now + timedelta(days=1),
            duration_minutes=20,
        )
        edit_url = reverse("quizzes:quiz_edit", kwargs={"pk": quiz.pk})
        response = self.student_1_client.get(edit_url)
        self.assertEqual(response.status_code, 403)

    def test_question_authoring_and_marks_sync(self):
        """Lecturer can add questions with options and sync marks."""
        quiz = Quiz.objects.create(
            course=self.course_a,
            creator=self.lecturer_a,
            title="Question Manage Test Quiz",
            available_from=self.now,
            available_to=self.now + timedelta(days=2),
            duration_minutes=30,
            status=QuizStatus.DRAFT,
            total_marks=Decimal("0.00"),
        )
        add_q_url = reverse("quizzes:question_create", kwargs={"quiz_pk": quiz.pk})

        # Add Short Answer
        post_data = {
            "text": "Define ACID properties.",
            "question_type": QuestionType.SHORT_ANSWER,
            "marks": "5.00",
            "order": 1,
            "model_answer": "Atomicity, Consistency, Isolation, Durability.",
        }
        response = self.lecturer_a_client.post(add_q_url, data=post_data)
        self.assertEqual(response.status_code, 302)

        quiz.refresh_from_db()
        self.assertEqual(quiz.questions.count(), 1)
        self.assertEqual(quiz.total_marks, Decimal("5.00"))

    def test_course_quiz_results_roster_view(self):
        """Allocated lecturer can view roster and aggregate statistics."""
        quiz = Quiz.objects.create(
            course=self.course_a,
            creator=self.lecturer_a,
            title="Roster Test Quiz",
            available_from=self.now - timedelta(hours=1),
            available_to=self.now + timedelta(days=1),
            duration_minutes=30,
            status=QuizStatus.PUBLISHED,
            total_marks=Decimal("10.00"),
        )
        QuizAttempt.objects.create(
            quiz=quiz,
            student=self.student_1,
            attempt_number=1,
            status=AttemptStatus.COMPLETED,
            started_at=self.now,
            submitted_at=self.now,
            score_obtained=Decimal("8.00"),
            total_marks=Decimal("10.00"),
            percentage=Decimal("80.00"),
            is_passed=True,
        )

        roster_url = reverse("quizzes:course_quiz_results", kwargs={"quiz_pk": quiz.pk})
        response = self.lecturer_a_client.get(roster_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.student_1.get_full_name)
        self.assertContains(response, "8.00")
        self.assertContains(response, "Passed")
