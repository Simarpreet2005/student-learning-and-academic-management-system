"""Automated unit and integration test suite for the Rule-Based Smart Academic Workload Planner.

Covers:
1. Priority calculations, clustering, and deterministic task ordering.
2. Boundary conditions for workload classification (Balanced, Moderate, Heavy, Conflict).
3. Both configured and unconfigured study availability states.
4. Schedule generation and deficit detection.
5. Dynamic updates when deliverables (assignments/quizzes) are completed.
6. Role-based access control and strict boundary enforcement (Student, Lecturer, Parent, Admin).
"""
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ParentStudentRelationship, Role, StudentProfile, User
from apps.academics.models import Course, Department, EnrollmentStatus, StudentEnrollment, CourseAllocation
from apps.assessments.models import Assignment, AssignmentSubmission
from apps.planner.models import StudentStudyBudget, TaskEffortProfile
from apps.planner.services import (
    DeadlineCluster,
    PlannerTask,
    WorkloadPlannerService,
)
from apps.quizzes.models import AttemptStatus, Quiz, QuizAttempt, QuizStatus


class PlannerServiceUnitTests(TestCase):
    """Pure algorithmic and deterministic unit tests using fixed reference timestamps."""

    def setUp(self):
        self.ref_time = datetime(2026, 10, 20, 10, 0, 0, tzinfo=dt_timezone.utc)

    def test_detect_deadline_clusters_empty_and_single(self):
        """0 or 1 task produces zero clusters."""
        self.assertEqual(WorkloadPlannerService.detect_deadline_clusters([]), [])

        single_task = PlannerTask(
            task_id="t1",
            source_id=1,
            task_type="ASSIGNMENT",
            title="Essay",
            course_id=1,
            course_code="CS101",
            course_title="Intro",
            course_credits=3,
            deadline=self.ref_time + timedelta(days=2),
            start_date=self.ref_time,
            actual_duration_minutes=None,
            estimated_effort_hours=2.0,
            is_completed=False,
            completion_status="PENDING",
            is_overdue=False,
            days_remaining=2.0,
            hours_remaining=48.0,
        )
        self.assertEqual(WorkloadPlannerService.detect_deadline_clusters([single_task]), [])

    def test_detect_deadline_clusters_within_48h(self):
        """Tasks with deadlines within 48h are grouped into clusters with appropriate severity."""
        t1 = PlannerTask(
            task_id="t1", source_id=1, task_type="ASSIGNMENT", title="Task 1",
            course_id=1, course_code="CS101", course_title="Intro", course_credits=3,
            deadline=self.ref_time + timedelta(hours=10), start_date=self.ref_time,
            actual_duration_minutes=None, estimated_effort_hours=2.0,
            is_completed=False, completion_status="PENDING", is_overdue=False,
            days_remaining=0.4, hours_remaining=10.0,
        )
        t2 = PlannerTask(
            task_id="t2", source_id=2, task_type="QUIZ", title="Quiz 1",
            course_id=1, course_code="CS101", course_title="Intro", course_credits=3,
            deadline=self.ref_time + timedelta(hours=30), start_date=self.ref_time,
            actual_duration_minutes=45, estimated_effort_hours=None,
            is_completed=False, completion_status="PENDING", is_overdue=False,
            days_remaining=1.2, hours_remaining=30.0,
        )
        t3 = PlannerTask(
            task_id="t3", source_id=3, task_type="ASSIGNMENT", title="Task 3 Far",
            course_id=1, course_code="CS101", course_title="Intro", course_credits=3,
            deadline=self.ref_time + timedelta(days=10), start_date=self.ref_time,
            actual_duration_minutes=None, estimated_effort_hours=3.0,
            is_completed=False, completion_status="PENDING", is_overdue=False,
            days_remaining=10.0, hours_remaining=240.0,
        )

        clusters = WorkloadPlannerService.detect_deadline_clusters([t1, t2, t3], window_hours=48)
        self.assertEqual(len(clusters), 1)
        c = clusters[0]
        self.assertEqual(c.task_count, 2)
        self.assertEqual(c.severity, "MODERATE")
        self.assertIn("t1", c.task_ids)
        self.assertIn("t2", c.task_ids)
        self.assertNotIn("t3", c.task_ids)

    def test_calculate_task_priorities_proximity_and_ordering(self):
        """Urgent tasks are scored higher and sorted ahead of distant or completed tasks."""
        t_urgent = PlannerTask(
            task_id="t_urg", source_id=1, task_type="ASSIGNMENT", title="Urgent Lab",
            course_id=1, course_code="CS101", course_title="Intro", course_credits=4,
            deadline=self.ref_time + timedelta(hours=12), start_date=self.ref_time,
            actual_duration_minutes=None, estimated_effort_hours=4.0,
            is_completed=False, completion_status="PENDING", is_overdue=False,
            days_remaining=0.5, hours_remaining=12.0,
        )
        t_distant = PlannerTask(
            task_id="t_dist", source_id=2, task_type="ASSIGNMENT", title="Distant Essay",
            course_id=1, course_code="CS101", course_title="Intro", course_credits=3,
            deadline=self.ref_time + timedelta(days=12), start_date=self.ref_time,
            actual_duration_minutes=None, estimated_effort_hours=2.0,
            is_completed=False, completion_status="PENDING", is_overdue=False,
            days_remaining=12.0, hours_remaining=288.0,
        )
        t_overdue = PlannerTask(
            task_id="t_over", source_id=3, task_type="ASSIGNMENT", title="Late Assignment",
            course_id=1, course_code="CS101", course_title="Intro", course_credits=3,
            deadline=self.ref_time - timedelta(days=1), start_date=self.ref_time - timedelta(days=5),
            actual_duration_minutes=None, estimated_effort_hours=2.0,
            is_completed=False, completion_status="PENDING", is_overdue=True,
            days_remaining=-1.0, hours_remaining=-24.0,
        )
        t_done = PlannerTask(
            task_id="t_done", source_id=4, task_type="QUIZ", title="Completed Quiz",
            course_id=1, course_code="CS101", course_title="Intro", course_credits=3,
            deadline=self.ref_time + timedelta(days=2), start_date=self.ref_time,
            actual_duration_minutes=30, estimated_effort_hours=None,
            is_completed=True, completion_status="GRADED", is_overdue=False,
            days_remaining=2.0, hours_remaining=48.0,
        )

        pending, completed = WorkloadPlannerService.calculate_task_priorities(
            [t_urgent, t_distant, t_overdue, t_done],
            clusters=[],
            reference_time=self.ref_time,
        )

        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0].task_id, "t_done")
        self.assertEqual(completed[0].priority_level, "COMPLETED")

        self.assertEqual(len(pending), 3)
        # Order should be Overdue (110) -> Urgent (Critical) -> Distant (Low)
        self.assertEqual(pending[0].task_id, "t_over")
        self.assertEqual(pending[0].priority_level, "OVERDUE")

        self.assertEqual(pending[1].task_id, "t_urg")
        self.assertEqual(pending[1].priority_level, "CRITICAL")
        self.assertIn("Critical Proximity", pending[1].priority_explanation)

        self.assertEqual(pending[2].task_id, "t_dist")
        self.assertEqual(pending[2].priority_level, "LOW")

    def test_classify_workload_unconfigured_budget_thresholds(self):
        """When study budget is None, categorizes by task count and clusters without guessing free time."""
        # 1 task -> BALANCED
        t1 = PlannerTask(
            task_id="t1", source_id=1, task_type="ASSIGNMENT", title="T1",
            course_id=1, course_code="CS101", course_title="Intro", course_credits=3,
            deadline=self.ref_time + timedelta(days=3), start_date=self.ref_time,
            actual_duration_minutes=None, estimated_effort_hours=2.0,
            is_completed=False, completion_status="PENDING", is_overdue=False,
            days_remaining=3.0, hours_remaining=72.0,
        )
        lvl, label, _, _, util = WorkloadPlannerService.classify_workload(
            [t1], budget=None, clusters=[], reference_time=self.ref_time, horizon_days=7
        )
        self.assertEqual(lvl, "BALANCED")
        self.assertIsNone(util)

        # 2 tasks -> MODERATE
        t2 = PlannerTask(
            task_id="t2", source_id=2, task_type="ASSIGNMENT", title="T2",
            course_id=1, course_code="CS101", course_title="Intro", course_credits=3,
            deadline=self.ref_time + timedelta(days=5), start_date=self.ref_time,
            actual_duration_minutes=None, estimated_effort_hours=2.0,
            is_completed=False, completion_status="PENDING", is_overdue=False,
            days_remaining=5.0, hours_remaining=120.0,
        )
        lvl, label, _, _, _ = WorkloadPlannerService.classify_workload(
            [t1, t2], budget=None, clusters=[], reference_time=self.ref_time, horizon_days=7
        )
        self.assertEqual(lvl, "MODERATE")

        # 4 tasks -> HEAVY
        t3 = PlannerTask(
            task_id="t3", source_id=3, task_type="ASSIGNMENT", title="T3",
            course_id=1, course_code="CS101", course_title="Intro", course_credits=3,
            deadline=self.ref_time + timedelta(days=2), start_date=self.ref_time,
            actual_duration_minutes=None, estimated_effort_hours=2.0,
            is_completed=False, completion_status="PENDING", is_overdue=False,
            days_remaining=2.0, hours_remaining=48.0,
        )
        t4 = PlannerTask(
            task_id="t4", source_id=4, task_type="ASSIGNMENT", title="T4",
            course_id=1, course_code="CS101", course_title="Intro", course_credits=3,
            deadline=self.ref_time + timedelta(days=6), start_date=self.ref_time,
            actual_duration_minutes=None, estimated_effort_hours=2.0,
            is_completed=False, completion_status="PENDING", is_overdue=False,
            days_remaining=6.0, hours_remaining=144.0,
        )
        lvl, label, _, _, _ = WorkloadPlannerService.classify_workload(
            [t1, t2, t3, t4], budget=None, clusters=[], reference_time=self.ref_time, horizon_days=7
        )
        self.assertEqual(lvl, "HEAVY")

        # 5 tasks -> CONFLICT
        t5 = PlannerTask(
            task_id="t5", source_id=5, task_type="QUIZ", title="T5",
            course_id=1, course_code="CS101", course_title="Intro", course_credits=3,
            deadline=self.ref_time + timedelta(days=4), start_date=self.ref_time,
            actual_duration_minutes=30, estimated_effort_hours=None,
            is_completed=False, completion_status="PENDING", is_overdue=False,
            days_remaining=4.0, hours_remaining=96.0,
        )
        lvl, label, _, _, _ = WorkloadPlannerService.classify_workload(
            [t1, t2, t3, t4, t5], budget=None, clusters=[], reference_time=self.ref_time, horizon_days=7
        )
        self.assertEqual(lvl, "CONFLICT")

    def test_classify_workload_configured_budget_thresholds(self):
        """When study budget is configured, categorizes by effort-to-availability ratio."""
        # Mock a budget with 10 hours weekly availability
        budget = StudentStudyBudget(
            monday_hours=Decimal("2.0"),
            tuesday_hours=Decimal("2.0"),
            wednesday_hours=Decimal("2.0"),
            thursday_hours=Decimal("2.0"),
            friday_hours=Decimal("2.0"),
            saturday_hours=Decimal("0.0"),
            sunday_hours=Decimal("0.0"),
        )
        self.assertEqual(budget.target_weekly_hours, Decimal("10.0"))

        # Task with 3 hours effort: Ratio = 3.0 / 10.0 = 0.30 <= 0.40 -> BALANCED
        t_low = PlannerTask(
            task_id="t_low", source_id=1, task_type="ASSIGNMENT", title="Low",
            course_id=1, course_code="CS101", course_title="Intro", course_credits=3,
            deadline=self.ref_time + timedelta(days=3), start_date=self.ref_time,
            actual_duration_minutes=None, estimated_effort_hours=3.0,
            is_completed=False, completion_status="PENDING", is_overdue=False,
            days_remaining=3.0, hours_remaining=72.0,
        )
        lvl, _, _, _, util = WorkloadPlannerService.classify_workload(
            [t_low], budget=budget, clusters=[], reference_time=self.ref_time, horizon_days=7
        )
        self.assertEqual(lvl, "BALANCED")
        self.assertEqual(util, 30.0)

        # 6 hours effort: Ratio = 6.0 / 10.0 = 0.60 -> MODERATE
        t_mod = PlannerTask(
            task_id="t_mod", source_id=2, task_type="ASSIGNMENT", title="Mod",
            course_id=1, course_code="CS101", course_title="Intro", course_credits=3,
            deadline=self.ref_time + timedelta(days=4), start_date=self.ref_time,
            actual_duration_minutes=None, estimated_effort_hours=6.0,
            is_completed=False, completion_status="PENDING", is_overdue=False,
            days_remaining=4.0, hours_remaining=96.0,
        )
        lvl, _, _, _, util = WorkloadPlannerService.classify_workload(
            [t_mod], budget=budget, clusters=[], reference_time=self.ref_time, horizon_days=7
        )
        self.assertEqual(lvl, "MODERATE")
        self.assertEqual(util, 60.0)

        # 10 hours effort: Ratio = 10.0 / 10.0 = 1.0 -> HEAVY
        t_hvy = PlannerTask(
            task_id="t_hvy", source_id=3, task_type="ASSIGNMENT", title="Hvy",
            course_id=1, course_code="CS101", course_title="Intro", course_credits=3,
            deadline=self.ref_time + timedelta(days=5), start_date=self.ref_time,
            actual_duration_minutes=None, estimated_effort_hours=10.0,
            is_completed=False, completion_status="PENDING", is_overdue=False,
            days_remaining=5.0, hours_remaining=120.0,
        )
        lvl, _, _, _, util = WorkloadPlannerService.classify_workload(
            [t_hvy], budget=budget, clusters=[], reference_time=self.ref_time, horizon_days=7
        )
        self.assertEqual(lvl, "HEAVY")
        self.assertEqual(util, 100.0)

        # 14 hours effort: Ratio = 14.0 / 10.0 = 1.40 > 1.25 -> CONFLICT
        t_conf = PlannerTask(
            task_id="t_conf", source_id=4, task_type="ASSIGNMENT", title="Conf",
            course_id=1, course_code="CS101", course_title="Intro", course_credits=3,
            deadline=self.ref_time + timedelta(days=5), start_date=self.ref_time,
            actual_duration_minutes=None, estimated_effort_hours=14.0,
            is_completed=False, completion_status="PENDING", is_overdue=False,
            days_remaining=5.0, hours_remaining=120.0,
        )
        lvl, _, _, _, util = WorkloadPlannerService.classify_workload(
            [t_conf], budget=budget, clusters=[], reference_time=self.ref_time, horizon_days=7
        )
        self.assertEqual(lvl, "CONFLICT")
        self.assertEqual(util, 140.0)

    def test_generate_study_schedule_unconfigured_returns_none(self):
        """If budget is None, generate_study_schedule strictly returns None without guessing."""
        self.assertIsNone(
            WorkloadPlannerService.generate_study_schedule([], budget=None, reference_time=self.ref_time)
        )

    def test_generate_study_schedule_deficit_detection(self):
        """Schedule accurately allocates study blocks and triggers deficit alert when effort > capacity."""
        # 7-day budget: 1 hour each day = 7 hours total
        budget = StudentStudyBudget(
            monday_hours=Decimal("1.0"),
            tuesday_hours=Decimal("1.0"),
            wednesday_hours=Decimal("1.0"),
            thursday_hours=Decimal("1.0"),
            friday_hours=Decimal("1.0"),
            saturday_hours=Decimal("1.0"),
            sunday_hours=Decimal("1.0"),
        )
        # Task requires 10 hours of effort
        task = PlannerTask(
            task_id="t1", source_id=1, task_type="ASSIGNMENT", title="Big Project",
            course_id=1, course_code="CS101", course_title="Intro", course_credits=3,
            deadline=self.ref_time + timedelta(days=6), start_date=self.ref_time,
            actual_duration_minutes=None, estimated_effort_hours=10.0,
            is_completed=False, completion_status="PENDING", is_overdue=False,
            days_remaining=6.0, hours_remaining=144.0,
        )

        schedule = WorkloadPlannerService.generate_study_schedule(
            [task], budget=budget, reference_time=self.ref_time
        )
        self.assertIsNotNone(schedule)
        self.assertEqual(schedule.total_available_hours, 7.0)
        self.assertEqual(schedule.total_allocated_hours, 7.0)
        self.assertTrue(schedule.has_deficit)
        self.assertEqual(schedule.deficit_hours, 3.0)
        self.assertIn("Deficit Alert", schedule.notes[0])


class PlannerIntegrationAndDatabaseTests(TestCase):
    """End-to-end integration tests using active database models."""

    def setUp(self):
        self.department = Department.objects.create(name="Computer Science", code="CS")
        self.lecturer = User.objects.create_user(
            email="prof.turing@example.com",
            username="pturing",
            first_name="Alan",
            last_name="Turing",
            role=Role.LECTURER,
        )
        self.student = User.objects.create_user(
            email="ada.lovelace@example.com",
            username="alovelace",
            first_name="Ada",
            last_name="Lovelace",
            role=Role.STUDENT,
        )
        self.student_profile = StudentProfile.objects.create(
            user=self.student,
            student_id="STD-2026-001",
        )

        self.course = Course.objects.create(
            department=self.department,
            title="Algorithms & Data Structures",
            code="CS201",
            credits=3,
        )
        self.allocation = CourseAllocation.objects.create(
            course=self.course,
            lecturer=self.lecturer,
        )
        self.enrollment = StudentEnrollment.objects.create(
            course=self.course,
            student=self.student,
            status=EnrollmentStatus.ENROLLED,
        )

        self.ref_time = timezone.now()

    def test_collect_student_tasks_includes_assignment_and_quiz(self):
        """Tasks from enrolled courses are collected with exact deadlines and effort attributes."""
        assignment = Assignment.objects.create(
            course=self.course,
            created_by=self.lecturer,
            title="Graph Algorithms Lab",
            due_date=self.ref_time + timedelta(days=3),
            estimated_effort_hours=Decimal("4.5"),
            is_published=True,
        )
        quiz = Quiz.objects.create(
            course=self.course,
            creator=self.lecturer,
            title="Sorting Quiz",
            available_from=self.ref_time - timedelta(days=1),
            available_to=self.ref_time + timedelta(days=2),
            duration_minutes=45,
            status=QuizStatus.PUBLISHED,
        )

        summary = WorkloadPlannerService.get_student_workload(self.student, reference_time=self.ref_time)
        self.assertEqual(summary.total_pending_tasks, 2)
        self.assertEqual(summary.total_completed_tasks, 0)
        self.assertFalse(summary.is_configured)  # No budget created yet

        task_ids = [t.task_id for t in summary.prioritized_tasks]
        self.assertIn(f"assignment_{assignment.id}", task_ids)
        self.assertIn(f"quiz_{quiz.id}", task_ids)

        # Verify effort/duration preservation
        a_task = next(t for t in summary.prioritized_tasks if t.task_id == f"assignment_{assignment.id}")
        self.assertTrue(a_task.has_estimated_effort)
        self.assertEqual(a_task.estimated_effort_hours, 4.5)
        self.assertFalse(a_task.has_actual_duration)

        q_task = next(t for t in summary.prioritized_tasks if t.task_id == f"quiz_{quiz.id}")
        self.assertTrue(q_task.has_actual_duration)
        self.assertEqual(q_task.actual_duration_minutes, 45)
        self.assertFalse(q_task.has_estimated_effort)

    def test_completed_deliverables_excluded_from_active_workload(self):
        """Submitting an assignment or finishing a quiz immediately excludes it from pending tasks."""
        assignment = Assignment.objects.create(
            course=self.course,
            created_by=self.lecturer,
            title="Dynamic Programming",
            due_date=self.ref_time + timedelta(days=2),
            estimated_effort_hours=Decimal("5.0"),
            is_published=True,
        )
        quiz = Quiz.objects.create(
            course=self.course,
            creator=self.lecturer,
            title="Trees & Heaps Quiz",
            available_from=self.ref_time - timedelta(days=1),
            available_to=self.ref_time + timedelta(days=3),
            duration_minutes=30,
            status=QuizStatus.PUBLISHED,
        )

        # Before completion
        s_initial = WorkloadPlannerService.get_student_workload(self.student, reference_time=self.ref_time)
        self.assertEqual(s_initial.total_pending_tasks, 2)
        self.assertEqual(s_initial.total_completed_tasks, 0)

        # Complete assignment
        AssignmentSubmission.objects.create(
            assignment=assignment,
            student=self.student,
            status=AssignmentSubmission.SubmissionStatus.SUBMITTED,
        )

        # Complete quiz
        QuizAttempt.objects.create(
            quiz=quiz,
            student=self.student,
            status=AttemptStatus.SUBMITTED,
        )

        # After completion: both deliverables are now categorized as completed
        s_after = WorkloadPlannerService.get_student_workload(self.student, reference_time=self.ref_time)
        self.assertEqual(s_after.total_pending_tasks, 0)
        self.assertEqual(s_after.total_completed_tasks, 2)
        self.assertEqual(s_after.workload_level, "BALANCED")

    def test_non_enrolled_courses_excluded(self):
        """Deliverables from courses where student is not actively enrolled must not appear."""
        other_course = Course.objects.create(
            department=self.department,
            title="Quantum Computing",
            code="CS499",
            credits=3,
        )
        Assignment.objects.create(
            course=other_course,
            created_by=self.lecturer,
            title="Quantum Teleportation Lab",
            due_date=self.ref_time + timedelta(days=2),
            is_published=True,
        )

        summary = WorkloadPlannerService.get_student_workload(self.student, reference_time=self.ref_time)
        self.assertEqual(summary.total_pending_tasks, 0)


class PlannerPermissionsAndViewsTests(TestCase):
    """View endpoint tests verifying role permissions and IDOR isolation."""

    def setUp(self):
        self.client = Client()
        self.department = Department.objects.create(name="Mathematics", code="MATH")

        self.lecturer = User.objects.create_user(
            email="dr.euler@example.com",
            username="deuler",
            first_name="Leonhard",
            last_name="Euler",
            role=Role.LECTURER,
        )
        self.unallocated_lecturer = User.objects.create_user(
            email="dr.gauss@example.com",
            username="cgauss",
            first_name="Carl",
            last_name="Gauss",
            role=Role.LECTURER,
        )
        self.student = User.objects.create_user(
            email="student1@example.com",
            username="std1",
            first_name="Alice",
            last_name="Smith",
            role=Role.STUDENT,
        )
        self.other_student = User.objects.create_user(
            email="student2@example.com",
            username="std2",
            first_name="Bob",
            last_name="Jones",
            role=Role.STUDENT,
        )
        self.parent = User.objects.create_user(
            email="parent1@example.com",
            username="parent1",
            first_name="Carol",
            last_name="Smith",
            role=Role.PARENT,
        )
        self.unlinked_parent = User.objects.create_user(
            email="parent2@example.com",
            username="parent2",
            first_name="Dan",
            last_name="White",
            role=Role.PARENT,
        )
        self.admin = User.objects.create_user(
            email="admin@example.com",
            username="sysadmin",
            first_name="Institutional",
            last_name="Administrator",
            role=Role.ADMIN,
        )

        # Parent linkage
        ParentStudentRelationship.objects.create(
            parent=self.parent,
            student=self.student,
        )

        # Course and allocation
        self.course = Course.objects.create(
            department=self.department,
            title="Calculus I",
            code="MATH101",
            credits=4,
        )
        CourseAllocation.objects.create(
            course=self.course,
            lecturer=self.lecturer,
        )
        StudentEnrollment.objects.create(
            course=self.course,
            student=self.student,
            status=EnrollmentStatus.ENROLLED,
        )

    def test_anonymous_redirected_to_login(self):
        """Anonymous requests to planner views redirect to login."""
        response = self.client.get(reverse("planner:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_student_can_view_own_dashboard(self):
        """Enrolled student can view their personalized workload dashboard."""
        self.client.force_login(self.student)
        response = self.client.get(reverse("planner:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Smart Academic Workload Planner")
        self.assertContains(response, "Alice Smith")

    def test_student_can_configure_study_preferences(self):
        """Student can view and update their weekly study hours."""
        self.client.force_login(self.student)
        # GET preferences form
        resp_get = self.client.get(reverse("planner:preferences"))
        self.assertEqual(resp_get.status_code, 200)
        self.assertContains(resp_get, "Weekly Study Hours Availability")

        # POST update preferences
        post_data = {
            "monday_hours": "3.0",
            "tuesday_hours": "3.0",
            "wednesday_hours": "3.0",
            "thursday_hours": "3.0",
            "friday_hours": "3.0",
            "saturday_hours": "5.0",
            "sunday_hours": "5.0",
            "notes": "Focused morning study blocks",
        }
        resp_post = self.client.post(reverse("planner:preferences"), post_data)
        self.assertEqual(resp_post.status_code, 302)
        self.assertRedirects(resp_post, reverse("planner:dashboard"))

        # Verify DB update
        budget = StudentStudyBudget.objects.get(student=self.student)
        self.assertEqual(budget.target_weekly_hours, Decimal("25.0"))
        self.assertEqual(budget.notes, "Focused morning study blocks")

    def test_lecturer_cannot_access_student_preferences(self):
        """Lecturers cannot access student study preferences view."""
        self.client.force_login(self.lecturer)
        response = self.client.get(reverse("planner:preferences"))
        self.assertEqual(response.status_code, 403)

    def test_parent_cannot_access_student_preferences(self):
        """Parents cannot edit student study preferences (strictly read-only)."""
        self.client.force_login(self.parent)
        response = self.client.get(reverse("planner:preferences"))
        self.assertEqual(response.status_code, 403)

    def test_lecturer_can_view_allocated_course_workload(self):
        """Lecturer can view deliverable analytics for an allocated course."""
        self.client.force_login(self.lecturer)
        url = reverse("planner:course_workload", kwargs={"course_id": self.course.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "MATH101 — Deliverable Workload Analytics")

    def test_unallocated_lecturer_blocked_from_course_workload(self):
        """Lecturer not allocated to a course receives HTTP 403."""
        self.client.force_login(self.unallocated_lecturer)
        url = reverse("planner:course_workload", kwargs={"course_id": self.course.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_parent_can_view_linked_student_workload(self):
        """Parent can view the read-only workload summary of an explicitly linked student."""
        self.client.force_login(self.parent)
        url = reverse("planner:student_workload", kwargs={"student_id": self.student.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Academic Workload: Alice Smith")
        self.assertContains(response, "Authorized Parent Observer")

    def test_unlinked_parent_blocked_from_student_workload(self):
        """Parent attempting to view an unlinked student receives HTTP 403."""
        self.client.force_login(self.unlinked_parent)
        url = reverse("planner:student_workload", kwargs={"student_id": self.student.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_admin_can_access_student_planner_and_picker(self):
        """Admin can access directory picker and inspect any student's plan."""
        self.client.force_login(self.admin)
        # Picker directory
        resp_dir = self.client.get(reverse("planner:dashboard"))
        self.assertEqual(resp_dir.status_code, 200)
        self.assertContains(resp_dir, "Student Workload Planner Oversight")

        # Specific student plan
        resp_std = self.client.get(f"{reverse('planner:dashboard')}?student_id={self.student.id}")
        self.assertEqual(resp_std.status_code, 200)
        self.assertContains(resp_std, "Alice Smith")
