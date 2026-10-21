from datetime import timedelta
from decimal import Decimal
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Student, User
from assignment.models import Assignment, AssignmentSubmission
from course.models import Course, CourseAllocation, Program
from core.models import Notification
from result.models import TakenCourse


class NotificationTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Create Program
        self.program = Program.objects.create(title="Computer Science")

        # Create Lecturer
        self.lecturer = User.objects.create_user(
            username="lec_notif",
            email="lec_notif@test.com",
            password="lecpassword123",
            is_lecturer=True,
        )

        # Create Course
        self.course = Course.objects.create(
            title="Database Systems",
            code="CS201",
            credit=3,
            program=self.program,
            level="Bachelor",
            year=2,
            semester="First",
        )

        # Allocate Course to Lecturer
        self.allocation = CourseAllocation.objects.create(lecturer=self.lecturer)
        self.allocation.courses.add(self.course)

        # Create Student 1 (Enrolled)
        self.student1_user = User.objects.create_user(
            username="stud_enrolled",
            email="stud_enrolled@test.com",
            password="studpassword123",
            is_student=True,
        )
        self.student1 = Student.objects.create(
            student=self.student1_user,
            program=self.program,
            level="Bachelor",
        )
        TakenCourse.objects.create(student=self.student1, course=self.course)

        # Create Student 2 (Unenrolled)
        self.student2_user = User.objects.create_user(
            username="stud_other",
            email="stud_other@test.com",
            password="studpassword123",
            is_student=True,
        )
        self.student2 = Student.objects.create(
            student=self.student2_user,
            program=self.program,
            level="Bachelor",
        )

    def test_notification_created_on_new_assignment(self):
        """When an assignment is created, enrolled students receive a notification."""
        self.client.force_login(self.lecturer)
        create_url = reverse("assignment_create", kwargs={"slug": self.course.slug})

        due_date = timezone.now() + timedelta(days=5)
        post_data = {
            "title": "SQL Homework 1",
            "description": "Write basic SELECT queries.",
            "due_date": due_date.strftime("%Y-%m-%dT%H:%M"),
            "maximum_marks": "20.00",
            "allow_resubmission": "on",
        }

        response = self.client.post(create_url, data=post_data)
        self.assertEqual(response.status_code, 302)

        # Check notification for enrolled student
        stud1_notifications = Notification.objects.filter(user=self.student1_user)
        self.assertEqual(stud1_notifications.count(), 1)
        notif = stud1_notifications.first()
        self.assertEqual(notif.notification_type, "assignment_created")
        self.assertIn("SQL Homework 1", notif.title)
        self.assertFalse(notif.is_read)

        # Check unenrolled student did not receive notification
        stud2_notifications = Notification.objects.filter(user=self.student2_user)
        self.assertEqual(stud2_notifications.count(), 0)

    def test_notification_created_on_submission_graded(self):
        """When a submission is graded, the student receives a notification."""
        # Create assignment
        assignment = Assignment.objects.create(
            course=self.course,
            created_by=self.lecturer,
            title="SQL Homework 1",
            description="Write basic SELECT queries.",
            due_date=timezone.now() + timedelta(days=5),
            maximum_marks=Decimal("20.00"),
        )

        # Create submission
        submission = AssignmentSubmission.objects.create(
            assignment=assignment,
            student=self.student1,
            file="assignments/submissions/test.txt",
        )

        self.client.force_login(self.lecturer)
        grade_url = reverse("submission_grade", kwargs={"pk": submission.pk})
        post_data = {
            "marks": "18.50",
            "feedback": "Great query structure, minor indexing comment.",
        }

        response = self.client.post(grade_url, data=post_data)
        self.assertEqual(response.status_code, 302)

        submission.refresh_from_db()
        self.assertEqual(submission.marks, Decimal("18.50"))

        # Check notification for the student
        stud_notifs = Notification.objects.filter(
            user=self.student1_user, notification_type="assignment_graded"
        )
        self.assertEqual(stud_notifs.count(), 1)
        notif = stud_notifs.first()
        self.assertIn("18.5", notif.message)
        self.assertFalse(notif.is_read)

    def test_notification_list_view(self):
        """User can view their list of notifications."""
        Notification.objects.create(
            user=self.student1_user,
            title="Test Notice",
            message="Notice content",
            notification_type="general",
        )

        self.client.force_login(self.student1_user)
        response = self.client.get(reverse("notification_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Notice")
        self.assertEqual(response.context["unread_count"], 1)

    def test_mark_notification_read(self):
        """User can mark a single notification as read and get redirected."""
        notif = Notification.objects.create(
            user=self.student1_user,
            title="Graded Notice",
            message="Your work was graded.",
            notification_type="assignment_graded",
            link="/assignments/1/",
        )

        self.client.force_login(self.student1_user)
        read_url = reverse("mark_notification_read", kwargs={"pk": notif.pk})
        response = self.client.get(read_url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/assignments/1/")

        notif.refresh_from_db()
        self.assertTrue(notif.is_read)

    def test_mark_all_notifications_read(self):
        """User can mark all notifications as read in one action."""
        Notification.objects.create(
            user=self.student1_user,
            title="Notice 1",
            message="Msg 1",
            is_read=False,
        )
        Notification.objects.create(
            user=self.student1_user,
            title="Notice 2",
            message="Msg 2",
            is_read=False,
        )

        self.client.force_login(self.student1_user)
        response = self.client.get(reverse("mark_all_notifications_read"))
        self.assertEqual(response.status_code, 302)

        unread_count = Notification.objects.filter(
            user=self.student1_user, is_read=False
        ).count()
        self.assertEqual(unread_count, 0)

    def test_user_cannot_mark_other_users_notification_read(self):
        """A user cannot mark another user's notification as read (IDOR prevention)."""
        notif = Notification.objects.create(
            user=self.student1_user,
            title="Private Notice",
            message="Confidential",
            is_read=False,
        )

        # Login as student 2
        self.client.force_login(self.student2_user)
        read_url = reverse("mark_notification_read", kwargs={"pk": notif.pk})
        response = self.client.get(read_url)
        self.assertEqual(response.status_code, 404)

        notif.refresh_from_db()
        self.assertFalse(notif.is_read)
