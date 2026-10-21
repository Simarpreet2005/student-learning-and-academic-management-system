"""Automated tests for Core and Phase 8 Academic Calendar & Dashboards."""
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import (
    LecturerProfile,
    ParentProfile,
    ParentStudentRelationship,
    RelationshipType,
    Role,
    StudentProfile,
)
from apps.academics.models import (
    AcademicProgram,
    AcademicYear,
    Course,
    CourseAllocation,
    Department,
    EnrollmentStatus,
    Semester,
    StudentEnrollment,
)
from apps.assessments.models import Assignment, AssignmentSubmission
from apps.core.models import AcademicEvent, EventType
from apps.core.services import CalendarService
from apps.courseware.models import CourseModule, LearningResource, ResourceStatus
from apps.quizzes.models import AttemptStatus, Quiz, QuizAttempt, QuizStatus

User = get_user_model()


class CoreViewsTestCase(TestCase):
    """Test suite for core views and baseline layout rendering."""

    def setUp(self):
        self.client = Client()

    def test_homepage_renders_successfully(self):
        """Homepage must return status code 200 and load the core template."""
        response = self.client.get(reverse("core:index"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/index.html")
        self.assertTemplateUsed(response, "base.html")

    def test_homepage_contains_branding_and_roles(self):
        """Homepage must display system branding, English text, and all four roles."""
        response = self.client.get(reverse("core:index"))
        content = response.content.decode("utf-8")
        self.assertIn("Academic LMS", content)
        self.assertIn("Administrator", content)
        self.assertIn("Lecturer", content)
        self.assertIn("Student", content)
        self.assertIn("Parent", content)

    def test_design_system_tokens_present(self):
        """Homepage must link to theme.css containing brown-and-cream design tokens."""
        response = self.client.get(reverse("core:index"))
        content = response.content.decode("utf-8")
        self.assertIn("/static/css/theme.css", content)
        self.assertIn("/static/css/components.css", content)


class AcademicEventModelTestCase(TestCase):
    """Test suite for AcademicEvent data model and validation."""

    def setUp(self):
        self.now = timezone.now()

    def test_create_academic_event_success(self):
        """Valid AcademicEvent is created with correct defaults."""
        event = AcademicEvent.objects.create(
            title="Matriculation Ceremony",
            event_type=EventType.CEREMONY,
            start_date=self.now + timedelta(days=1),
            end_date=self.now + timedelta(days=2),
            location="University Auditorium",
        )
        self.assertEqual(str(event), f"Matriculation Ceremony ({event.get_event_type_display()})")
        self.assertTrue(event.is_published)

    def test_academic_event_date_validation(self):
        """End date cannot precede start date."""
        event = AcademicEvent(
            title="Invalid Date Event",
            event_type=EventType.EXAMINATION,
            start_date=self.now + timedelta(days=5),
            end_date=self.now + timedelta(days=2),
        )
        with self.assertRaises(ValidationError):
            event.clean()


class CalendarServiceAndViewsTestCase(TestCase):
    """Test suite for CalendarService aggregation, role-scoping, and calendar views."""

    def setUp(self):
        self.client = Client()
        self.now = timezone.now()
        self.today = self.now.date()

        # Users
        self.admin = User.objects.create_user(
            username="cal_admin",
            email="cal_admin@lms.local",
            password="testpass123",
            role=Role.ADMIN,
        )
        self.lecturer = User.objects.create_user(
            username="cal_lecturer",
            email="cal_lecturer@lms.local",
            password="testpass123",
            role=Role.LECTURER,
        )
        LecturerProfile.objects.create(user=self.lecturer, employee_id="LEC-CAL-1")

        self.student = User.objects.create_user(
            username="cal_student",
            email="cal_student@lms.local",
            password="testpass123",
            role=Role.STUDENT,
        )
        StudentProfile.objects.create(user=self.student, student_id="STD-CAL-1")

        self.parent = User.objects.create_user(
            username="cal_parent",
            email="cal_parent@lms.local",
            password="testpass123",
            role=Role.PARENT,
        )
        ParentProfile.objects.create(user=self.parent)
        ParentStudentRelationship.objects.create(
            parent=self.parent,
            student=self.student,
            relationship_type=RelationshipType.FATHER,
        )

        # Unrelated student
        self.other_student = User.objects.create_user(
            username="other_student",
            email="other_student@lms.local",
            password="testpass123",
            role=Role.STUDENT,
        )
        StudentProfile.objects.create(user=self.other_student, student_id="STD-OTHER-1")

        # Academic structure
        self.department = Department.objects.create(name="Calendar CS", code="CSCAL")
        self.year = AcademicYear.objects.create(
            name="2026/2027 CAL",
            start_date=self.today - timedelta(days=30),
            end_date=self.today + timedelta(days=300),
            is_current=True,
        )
        self.semester = Semester.objects.create(
            academic_year=self.year,
            name="Fall 2026 CAL",
            start_date=self.today - timedelta(days=10),
            end_date=self.today + timedelta(days=120),
            is_active=True,
        )

        # Courses
        self.course1 = Course.objects.create(
            code="CS101-CAL",
            title="Intro to Computing CAL",
            department=self.department,
        )
        self.course2 = Course.objects.create(
            code="CS201-CAL",
            title="Data Structures CAL",
            department=self.department,
        )

        # Allocation: lecturer on course1
        CourseAllocation.objects.create(
            course=self.course1,
            lecturer=self.lecturer,
            semester=self.semester,
            is_active=True,
        )

        # Enrollment: student in course1
        StudentEnrollment.objects.create(
            student=self.student,
            course=self.course1,
            semester=self.semester,
            status=EnrollmentStatus.ENROLLED,
            is_active=True,
        )

        # Enrollment: other_student in course2
        StudentEnrollment.objects.create(
            student=self.other_student,
            course=self.course2,
            semester=self.semester,
            status=EnrollmentStatus.ENROLLED,
            is_active=True,
        )

        # Academic Events
        self.event_general = AcademicEvent.objects.create(
            title="University Convocation",
            event_type=EventType.CEREMONY,
            start_date=self.now + timedelta(days=5),
            is_published=True,
        )
        self.event_draft = AcademicEvent.objects.create(
            title="Internal Staff Draft Meeting",
            event_type=EventType.ACADEMIC,
            start_date=self.now + timedelta(days=7),
            is_published=False,
        )

        # Assignment in course1
        self.assignment_c1 = Assignment.objects.create(
            course=self.course1,
            created_by=self.lecturer,
            title="Homework 1 CAL",
            due_date=self.now + timedelta(days=4),
            is_published=True,
            is_active=True,
        )
        # Assignment in course2 (unrelated to student & lecturer)
        self.assignment_c2 = Assignment.objects.create(
            course=self.course2,
            created_by=self.admin,
            title="Homework 2 Other Course",
            due_date=self.now + timedelta(days=6),
            is_published=True,
            is_active=True,
        )

        # Quiz in course1
        self.quiz_c1 = Quiz.objects.create(
            course=self.course1,
            creator=self.lecturer,
            title="Quiz 1 CAL",
            duration_minutes=30,
            status=QuizStatus.PUBLISHED,
            available_from=self.now,
            available_to=self.now + timedelta(days=8),
        )

    def test_calendar_service_scoping_for_student(self):
        """Students see institutional events + assignments/quizzes only for enrolled courses."""
        events = CalendarService.get_user_events(
            user=self.student,
            start_bound=self.now - timedelta(days=1),
            end_bound=self.now + timedelta(days=30),
        )
        event_titles = [e.title for e in events]
        # General event included
        self.assertIn("University Convocation", event_titles)
        # Draft event excluded
        self.assertNotIn("Internal Staff Draft Meeting", event_titles)
        # Course 1 assignment & quiz included
        self.assertIn("CS101-CAL: Homework 1 CAL", event_titles)
        self.assertIn("CS101-CAL: Quiz 1 CAL", event_titles)
        # Course 2 assignment excluded (student not enrolled)
        self.assertNotIn("CS201-CAL: Homework 2 Other Course", event_titles)

    def test_calendar_service_scoping_for_lecturer(self):
        """Lecturers see institutional events + deliverables for their allocated courses."""
        events = CalendarService.get_user_events(
            user=self.lecturer,
            start_bound=self.now - timedelta(days=1),
            end_bound=self.now + timedelta(days=30),
        )
        event_titles = [e.title for e in events]
        self.assertIn("University Convocation", event_titles)
        self.assertIn("CS101-CAL: Homework 1 CAL", event_titles)
        self.assertIn("CS101-CAL: Quiz 1 CAL", event_titles)
        # Course 2 deliverable excluded
        self.assertNotIn("CS201-CAL: Homework 2 Other Course", event_titles)

    def test_calendar_service_scoping_for_parent(self):
        """Parents see deliverables for their verified linked child."""
        events = CalendarService.get_user_events(
            user=self.parent,
            target_student_id=self.student.pk,
            start_bound=self.now - timedelta(days=1),
            end_bound=self.now + timedelta(days=30),
        )
        event_titles = [e.title for e in events]
        self.assertIn("University Convocation", event_titles)
        self.assertIn("CS101-CAL: Homework 1 CAL", event_titles)
        self.assertNotIn("CS201-CAL: Homework 2 Other Course", event_titles)

    def test_calendar_service_filter_by_event_type(self):
        """Filtering by event_type returns only matching items."""
        events = CalendarService.get_user_events(
            user=self.student,
            event_type_filter="ASSIGNMENT",
            start_bound=self.now - timedelta(days=1),
            end_bound=self.now + timedelta(days=30),
        )
        for e in events:
            self.assertEqual(e.category, "ASSIGNMENT")

    def test_calendar_month_grid_structure(self):
        """build_month_grid produces 4 to 6 weeks with proper day cell dictionaries."""
        grid = CalendarService.build_month_grid(
            year=self.today.year,
            month=self.today.month,
            items=[],
        )
        self.assertGreaterEqual(len(grid), 4)
        self.assertLessEqual(len(grid), 6)
        first_week = grid[0]
        self.assertEqual(len(first_week), 7)
        self.assertIn("day_number", first_week[0])
        self.assertIn("is_current_month", first_week[0])
        self.assertIn("items", first_week[0])

    def test_calendar_view_anonymous_redirect(self):
        """Anonymous access to /calendar/ redirects to login."""
        response = self.client.get(reverse("core:calendar"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    def test_calendar_view_student_access_month_and_list(self):
        """Student can view month, week, and list views."""
        self.client.force_login(self.student)
        # Month view
        res_month = self.client.get(reverse("core:calendar") + "?view=month")
        self.assertEqual(res_month.status_code, 200)
        self.assertTemplateUsed(res_month, "core/calendar.html")

        # List view
        res_list = self.client.get(reverse("core:calendar") + "?view=list")
        self.assertEqual(res_list.status_code, 200)

        # Week view
        res_week = self.client.get(reverse("core:calendar") + "?view=week")
        self.assertEqual(res_week.status_code, 200)

    def test_calendar_view_parent_multi_child_scoping(self):
        """Parent views linked child's calendar; cannot access unlinked child."""
        self.client.force_login(self.parent)
        # Valid child
        res = self.client.get(f"{reverse('core:calendar')}?student_id={self.student.pk}")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context["active_student"], self.student)

        # Unlinked student ID falls back safely to first linked child
        res_unlinked = self.client.get(f"{reverse('core:calendar')}?student_id={self.other_student.pk}")
        self.assertEqual(res_unlinked.status_code, 200)
        self.assertNotEqual(res_unlinked.context["active_student"], self.other_student)


class DashboardViewsIntegrationTestCase(TestCase):
    """Integration test suite for role-specific performance dashboards."""

    def setUp(self):
        self.client = Client()
        self.now = timezone.now()
        self.today = self.now.date()

        # Users
        self.admin = User.objects.create_user(
            username="dash_admin",
            email="dash_admin@lms.local",
            password="testpass123",
            role=Role.ADMIN,
        )
        self.lecturer = User.objects.create_user(
            username="dash_lecturer",
            email="dash_lecturer@lms.local",
            password="testpass123",
            role=Role.LECTURER,
        )
        self.lecturer_profile = LecturerProfile.objects.create(
            user=self.lecturer, employee_id="LEC-DASH-1"
        )

        self.student = User.objects.create_user(
            username="dash_student",
            email="dash_student@lms.local",
            password="testpass123",
            role=Role.STUDENT,
        )
        self.student_profile = StudentProfile.objects.create(
            user=self.student, student_id="STD-DASH-1"
        )

        self.parent = User.objects.create_user(
            username="dash_parent",
            email="dash_parent@lms.local",
            password="testpass123",
            role=Role.PARENT,
        )
        ParentProfile.objects.create(user=self.parent)
        ParentStudentRelationship.objects.create(
            parent=self.parent,
            student=self.student,
            relationship_type=RelationshipType.MOTHER,
        )

        # Academics
        self.dept = Department.objects.create(name="Dash Dept", code="DASH")
        self.prog = AcademicProgram.objects.create(
            department=self.dept, name="B.Sc Dash", code="BSDASH"
        )
        self.year = AcademicYear.objects.create(
            name="2026/2027 DASH",
            start_date=self.today - timedelta(days=20),
            end_date=self.today + timedelta(days=200),
            is_current=True,
        )
        self.semester = Semester.objects.create(
            academic_year=self.year,
            name="Fall 2026 DASH",
            start_date=self.today - timedelta(days=10),
            end_date=self.today + timedelta(days=100),
            is_active=True,
        )
        self.course = Course.objects.create(
            code="DASH101",
            title="Dashboard Studies 101",
            department=self.dept,
            credits=3,
        )
        CourseAllocation.objects.create(
            course=self.course,
            lecturer=self.lecturer,
            semester=self.semester,
            is_active=True,
        )
        StudentEnrollment.objects.create(
            student=self.student,
            course=self.course,
            semester=self.semester,
            status=EnrollmentStatus.ENROLLED,
            is_active=True,
        )

        # Deliverables & Submissions
        self.assignment = Assignment.objects.create(
            course=self.course,
            created_by=self.lecturer,
            title="Dash Assignment 1",
            due_date=self.now + timedelta(days=3),
            estimated_effort_hours=Decimal("4.0"),
            is_published=True,
            is_active=True,
        )
        self.submission = AssignmentSubmission.objects.create(
            assignment=self.assignment,
            student=self.student,
            status=AssignmentSubmission.SubmissionStatus.SUBMITTED,
        )

        self.quiz = Quiz.objects.create(
            course=self.course,
            creator=self.lecturer,
            title="Dash Quiz 1",
            duration_minutes=20,
            status=QuizStatus.PUBLISHED,
            available_from=self.now,
            available_to=self.now + timedelta(days=5),
        )

    def test_student_dashboard_context_and_rendering(self):
        """Student dashboard loads enrolled courses, upcoming deliverables, workload, and events."""
        self.client.force_login(self.student)
        response = self.client.get(reverse("accounts:student_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/dashboards/student.html")
        self.assertIn("enrollments", response.context)
        self.assertIn("workload", response.context)
        self.assertIn("upcoming_assignments", response.context)
        self.assertIn("upcoming_quizzes", response.context)
        self.assertIn("recent_submissions", response.context)
        content = response.content.decode("utf-8")
        self.assertIn("DASH101", content)
        self.assertIn("Dash Assignment 1", content)

    def test_lecturer_dashboard_context_and_grading_queue(self):
        """Lecturer dashboard displays course allocations, pending submissions, and workload indicators."""
        self.client.force_login(self.lecturer)
        response = self.client.get(reverse("accounts:lecturer_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/dashboards/lecturer.html")
        self.assertIn("allocations", response.context)
        self.assertIn("pending_assignments_count", response.context)
        self.assertEqual(response.context["pending_assignments_count"], 1)
        self.assertIn("course_summaries", response.context)
        content = response.content.decode("utf-8")
        self.assertIn("DASH101", content)
        self.assertIn("Dash Assignment 1", content)

    def test_parent_dashboard_context_and_read_only_protection(self):
        """Parent dashboard displays linked child's courses, deadlines, and read-only notice."""
        self.client.force_login(self.parent)
        response = self.client.get(reverse("accounts:parent_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/dashboards/parent.html")
        self.assertIn("linked_students", response.context)
        self.assertEqual(response.context["selected_student"], self.student)
        content = response.content.decode("utf-8")
        self.assertIn("DASH101", content)
        self.assertIn("Strict Read-Only Access", content)

    def test_admin_dashboard_metrics_and_hierarchy(self):
        """Admin dashboard displays user counts, academic structure, and grading stats."""
        self.client.force_login(self.admin)
        response = self.client.get(reverse("accounts:admin_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/dashboards/admin.html")
        ctx = response.context
        self.assertGreaterEqual(ctx["total_users"], 4)
        self.assertEqual(ctx["department_count"], 1)
        self.assertEqual(ctx["course_count"], 1)
        self.assertEqual(ctx["enrollment_count"], 1)
        self.assertEqual(ctx["pending_assignments_count"], 1)
        content = response.content.decode("utf-8")
        self.assertIn("Administrator Dashboard", content)
        self.assertIn("Django Admin", content)
