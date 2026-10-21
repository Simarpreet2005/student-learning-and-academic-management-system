from datetime import timedelta
from decimal import Decimal
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Student, User
from course.models import Course, CourseAllocation, Program
from result.models import TakenCourse
from .models import Assignment, AssignmentSubmission


class AssignmentWorkflowTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Create Admin
        self.admin_user = User.objects.create_superuser(
            username="admin_user",
            email="admin@test.com",
            password="adminpassword123",
        )

        # Create Program
        self.program = Program.objects.create(title="Computer Science")

        # Create Lecturer 1 (allocated)
        self.lecturer1 = User.objects.create_user(
            username="lec_1",
            email="lec1@test.com",
            password="lecpassword123",
            is_lecturer=True,
        )

        # Create Lecturer 2 (unassigned)
        self.lecturer2 = User.objects.create_user(
            username="lec_2",
            email="lec2@test.com",
            password="lecpassword123",
            is_lecturer=True,
        )

        # Create Course
        self.course = Course.objects.create(
            title="Data Structures",
            code="CS101",
            credit=3,
            program=self.program,
            level="Bachelor",
            year=1,
            semester="First",
        )

        # Allocate Course to Lecturer 1
        self.allocation = CourseAllocation.objects.create(lecturer=self.lecturer1)
        self.allocation.courses.add(self.course)

        # Create Student 1 (enrolled)
        self.student1_user = User.objects.create_user(
            username="stud_1",
            email="stud1@test.com",
            password="studpassword123",
            is_student=True,
        )
        self.student1 = Student.objects.create(
            student=self.student1_user,
            program=self.program,
            level="Bachelor",
        )
        TakenCourse.objects.create(student=self.student1, course=self.course)

        # Create Student 2 (not enrolled in CS101)
        self.student2_user = User.objects.create_user(
            username="stud_2",
            email="stud2@test.com",
            password="studpassword123",
            is_student=True,
        )
        self.student2 = Student.objects.create(
            student=self.student2_user,
            program=self.program,
            level="Bachelor",
        )

        # Create test assignment
        self.assignment = Assignment.objects.create(
            course=self.course,
            created_by=self.lecturer1,
            title="Assignment 1: Linked Lists",
            description="Implement a singly linked list in Python.",
            due_date=timezone.now() + timedelta(days=7),
            maximum_marks=Decimal("50.00"),
            allow_resubmission=True,
        )

    def test_lecturer_can_create_assignment(self):
        """Allocated lecturer can create an assignment."""
        self.client.force_login(self.lecturer1)
        url = reverse("assignment_create", kwargs={"slug": self.course.slug})

        due_date_str = (timezone.now() + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M")
        data = {
            "title": "Assignment 2: Stacks",
            "description": "Implement a stack using arrays.",
            "due_date": due_date_str,
            "maximum_marks": "100.00",
            "allow_resubmission": True,
        }
        response = self.client.post(url, data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Assignment.objects.filter(title="Assignment 2: Stacks").exists())

    def test_unassigned_lecturer_cannot_create_assignment(self):
        """Lecturer not teaching the course cannot create an assignment."""
        self.client.force_login(self.lecturer2)
        url = reverse("assignment_create", kwargs={"slug": self.course.slug})

        due_date_str = (timezone.now() + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M")
        data = {
            "title": "Hacked Assignment",
            "description": "Unauthorized assignment creation",
            "due_date": due_date_str,
            "maximum_marks": "100.00",
        }
        response = self.client.post(url, data, follow=True)
        self.assertFalse(Assignment.objects.filter(title="Hacked Assignment").exists())

    def test_student_cannot_create_assignment(self):
        """Students cannot access the assignment creation endpoint."""
        self.client.force_login(self.student1_user)
        url = reverse("assignment_create", kwargs={"slug": self.course.slug})
        response = self.client.get(url, follow=False)
        self.assertEqual(response.status_code, 302)

    def test_enrolled_student_can_view_assignment(self):
        """Enrolled student can view assignment details."""
        self.client.force_login(self.student1_user)
        url = reverse("assignment_detail", kwargs={"slug": self.assignment.slug})
        response = self.client.get(url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Assignment 1: Linked Lists")

    def test_unenrolled_student_cannot_view_assignment(self):
        """Unenrolled student is redirected with an error when trying to view assignment."""
        self.client.force_login(self.student2_user)
        url = reverse("assignment_detail", kwargs={"slug": self.assignment.slug})
        response = self.client.get(url, follow=True)
        self.assertContains(response, "You do not have permission to view this assignment.")

    def test_student_can_submit_assignment_on_time(self):
        """Enrolled student can submit a valid file on time."""
        self.client.force_login(self.student1_user)
        url = reverse("assignment_submit", kwargs={"slug": self.assignment.slug})

        test_file = SimpleUploadedFile("solution.pdf", b"Dummy PDF content", content_type="application/pdf")
        data = {"file": test_file, "comment": "Here is my solution."}

        response = self.client.post(url, data, follow=True)
        self.assertEqual(response.status_code, 200)

        submission = AssignmentSubmission.objects.filter(assignment=self.assignment, student=self.student1).first()
        self.assertIsNotNone(submission)
        self.assertFalse(submission.is_late)
        self.assertEqual(submission.status, "submitted")
        self.assertEqual(submission.comment, "Here is my solution.")

    def test_student_late_submission_flagged(self):
        """Submission after due date is automatically flagged as late."""
        # Set due date to past
        self.assignment.due_date = timezone.now() - timedelta(days=1)
        self.assignment.save()

        self.client.force_login(self.student1_user)
        url = reverse("assignment_submit", kwargs={"slug": self.assignment.slug})

        test_file = SimpleUploadedFile("late_solution.pdf", b"Late PDF content", content_type="application/pdf")
        data = {"file": test_file, "comment": "Sorry for being late."}

        response = self.client.post(url, data, follow=True)
        self.assertEqual(response.status_code, 200)

        submission = AssignmentSubmission.objects.filter(assignment=self.assignment, student=self.student1).first()
        self.assertIsNotNone(submission)
        self.assertTrue(submission.is_late)
        self.assertEqual(submission.status, "submitted_late")

    def test_resubmission_policy_disallowed(self):
        """When allow_resubmission is False, a second submission is blocked."""
        self.assignment.allow_resubmission = False
        self.assignment.save()

        # First submission
        AssignmentSubmission.objects.create(
            assignment=self.assignment,
            student=self.student1,
            file=SimpleUploadedFile("first.pdf", b"First content"),
        )

        self.client.force_login(self.student1_user)
        url = reverse("assignment_submit", kwargs={"slug": self.assignment.slug})

        test_file = SimpleUploadedFile("second.pdf", b"Second content", content_type="application/pdf")
        response = self.client.post(url, {"file": test_file}, follow=True)
        self.assertContains(response, "Resubmissions are not permitted for this assignment.")

    def test_lecturer_can_grade_submission(self):
        """Lecturer can grade a student submission with marks and feedback."""
        submission = AssignmentSubmission.objects.create(
            assignment=self.assignment,
            student=self.student1,
            file=SimpleUploadedFile("student_work.pdf", b"Work content"),
        )

        self.client.force_login(self.lecturer1)
        url = reverse("submission_grade", kwargs={"pk": submission.pk})

        data = {"marks": "45.50", "feedback": "Great work on the linked list operations!"}
        response = self.client.post(url, data, follow=True)
        self.assertEqual(response.status_code, 200)

        submission.refresh_from_db()
        self.assertEqual(submission.marks, Decimal("45.50"))
        self.assertEqual(submission.feedback, "Great work on the linked list operations!")
        self.assertEqual(submission.status, "graded")
        self.assertEqual(submission.graded_by, self.lecturer1)
        self.assertIsNotNone(submission.graded_at)

    def test_grading_marks_cannot_exceed_maximum(self):
        """Marks cannot exceed maximum marks."""
        submission = AssignmentSubmission.objects.create(
            assignment=self.assignment,
            student=self.student1,
            file=SimpleUploadedFile("student_work.pdf", b"Work content"),
        )

        self.client.force_login(self.lecturer1)
        url = reverse("submission_grade", kwargs={"pk": submission.pk})

        # Maximum marks is 50.00; sending 60.00 should fail
        data = {"marks": "60.00", "feedback": "Too many marks"}
        response = self.client.post(url, data, follow=True)
        self.assertContains(response, "Marks cannot exceed the assignment maximum of 50.00.")

        submission.refresh_from_db()
        self.assertIsNone(submission.marks)

    def test_unauthorized_student_cannot_download_other_submission(self):
        """Student 2 cannot download Student 1's submission file (IDOR prevention)."""
        submission = AssignmentSubmission.objects.create(
            assignment=self.assignment,
            student=self.student1,
            file=SimpleUploadedFile("secret_solution.pdf", b"Secret Solution"),
        )

        self.client.force_login(self.student2_user)
        url = reverse("submission_download", kwargs={"pk": submission.pk})
        response = self.client.get(url, follow=True)
        self.assertEqual(response.status_code, 403)

    def test_assignment_status_properties(self):
        """Test upcoming, open, and closed statuses for Assignment."""
        now = timezone.now()

        # Open assignment (no start date, future due date)
        self.assertEqual(self.assignment.status, "open")
        self.assertEqual(self.assignment.status_label, "Open")
        self.assertTrue(self.assignment.is_open)
        self.assertFalse(self.assignment.is_upcoming)
        self.assertFalse(self.assignment.is_closed)

        # Upcoming assignment (future start date)
        upcoming_assignment = Assignment.objects.create(
            course=self.course,
            created_by=self.lecturer1,
            title="Upcoming Test",
            description="Opens next week",
            start_date=now + timedelta(days=2),
            due_date=now + timedelta(days=9),
            maximum_marks=Decimal("100.00"),
        )
        self.assertEqual(upcoming_assignment.status, "upcoming")
        self.assertEqual(upcoming_assignment.status_label, "Upcoming")
        self.assertTrue(upcoming_assignment.is_upcoming)
        self.assertFalse(upcoming_assignment.is_open)

        # Closed assignment (past due date)
        closed_assignment = Assignment.objects.create(
            course=self.course,
            created_by=self.lecturer1,
            title="Closed Test",
            description="Past deadline",
            due_date=now - timedelta(days=1),
            maximum_marks=Decimal("100.00"),
        )
        self.assertEqual(closed_assignment.status, "closed")
        self.assertEqual(closed_assignment.status_label, "Due/Closed")
        self.assertTrue(closed_assignment.is_closed)
        self.assertTrue(closed_assignment.is_past_due)

    def test_upcoming_assignment_blocks_student_submission(self):
        """Student cannot submit to an assignment before its start date."""
        upcoming_assignment = Assignment.objects.create(
            course=self.course,
            created_by=self.lecturer1,
            title="Future Assignment",
            description="Not yet open",
            start_date=timezone.now() + timedelta(days=3),
            due_date=timezone.now() + timedelta(days=10),
            maximum_marks=Decimal("100.00"),
        )

        self.client.force_login(self.student1_user)
        url = reverse("assignment_submit", kwargs={"slug": upcoming_assignment.slug})
        test_file = SimpleUploadedFile("early.pdf", b"Early work")
        response = self.client.post(url, {"file": test_file}, follow=True)
        self.assertContains(
            response,
            "This assignment is upcoming and not yet open for submissions.",
        )
        self.assertFalse(
            AssignmentSubmission.objects.filter(assignment=upcoming_assignment).exists()
        )

    def test_submission_status_labels(self):
        """Verify submission status labels and badge classes."""
        submission = AssignmentSubmission.objects.create(
            assignment=self.assignment,
            student=self.student1,
            file=SimpleUploadedFile("sub.pdf", b"Sub content"),
        )
        self.assertEqual(submission.status_label, "Submitted")
        self.assertEqual(submission.status_badge_class, "bg-primary")

        # Late submission
        submission.status = "submitted_late"
        submission.is_late = True
        submission.save()
        self.assertEqual(submission.status_label, "Submitted Late")

        # Graded submission
        submission.marks = Decimal("40.00")
        submission.save()
        self.assertEqual(submission.status_label, "Graded")
        self.assertEqual(submission.status_badge_class, "bg-success")

    def test_home_view_displays_assignment_widgets(self):
        """Home page renders assignment overview cards for student and lecturer."""
        # Student home view
        self.client.force_login(self.student1_user)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pending Submissions")
        self.assertContains(response, "My Assignments")

        # Lecturer home view
        self.client.force_login(self.lecturer1)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Total Assignments")
        self.assertContains(response, "Awaiting Grading")

    # ########################################################
    # AUTHENTICATION TESTS
    # ########################################################
    def test_unauthenticated_user_access_redirects_to_login(self):
        """Unauthenticated requests to protected assignment endpoints are redirected to login."""
        self.client.logout()

        protected_urls = [
            reverse("assignment_list", kwargs={"slug": self.course.slug}),
            reverse("assignment_create", kwargs={"slug": self.course.slug}),
            reverse("assignment_detail", kwargs={"slug": self.assignment.slug}),
            reverse("assignment_edit", kwargs={"slug": self.assignment.slug}),
            reverse("assignment_delete", kwargs={"slug": self.assignment.slug}),
            reverse("assignment_submit", kwargs={"slug": self.assignment.slug}),
            reverse("submission_list", kwargs={"slug": self.assignment.slug}),
            reverse("user_assignments"),
        ]

        for url in protected_urls:
            response = self.client.get(url)
            self.assertEqual(
                response.status_code,
                302,
                f"URL {url} did not redirect unauthenticated user",
            )
            self.assertIn("/accounts/login/", response.url)

    # ########################################################
    # LECTURER WORKFLOW & AUTHORIZATION TESTS
    # ########################################################
    def test_lecturer_can_edit_assignment(self):
        """Allocated lecturer can edit an existing assignment."""
        self.client.force_login(self.lecturer1)
        url = reverse("assignment_edit", kwargs={"slug": self.assignment.slug})

        due_date_str = (timezone.now() + timedelta(days=10)).strftime("%Y-%m-%dT%H:%M")
        data = {
            "title": "Assignment 1: Updated Title",
            "description": "Updated instructions.",
            "due_date": due_date_str,
            "maximum_marks": "75.00",
            "allow_resubmission": True,
        }
        response = self.client.post(url, data, follow=True)
        self.assertEqual(response.status_code, 200)

        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.title, "Assignment 1: Updated Title")
        self.assertEqual(self.assignment.maximum_marks, Decimal("75.00"))

    def test_unallocated_lecturer_cannot_edit_assignment(self):
        """Unallocated lecturer cannot edit another lecturer's assignment."""
        self.client.force_login(self.lecturer2)
        url = reverse("assignment_edit", kwargs={"slug": self.assignment.slug})

        due_date_str = (timezone.now() + timedelta(days=10)).strftime("%Y-%m-%dT%H:%M")
        data = {
            "title": "Hacked Title",
            "description": "Unauthorized edit",
            "due_date": due_date_str,
            "maximum_marks": "75.00",
        }
        response = self.client.post(url, data, follow=True)
        self.assertContains(
            response, "You are not authorized to edit this assignment."
        )

        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.title, "Assignment 1: Linked Lists")

    def test_lecturer_can_delete_assignment(self):
        """Allocated lecturer can delete an assignment."""
        self.client.force_login(self.lecturer1)
        url = reverse("assignment_delete", kwargs={"slug": self.assignment.slug})
        response = self.client.get(url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Assignment.objects.filter(pk=self.assignment.pk).exists())

    def test_unallocated_lecturer_cannot_delete_assignment(self):
        """Unallocated lecturer cannot delete another lecturer's assignment."""
        self.client.force_login(self.lecturer2)
        url = reverse("assignment_delete", kwargs={"slug": self.assignment.slug})
        response = self.client.get(url, follow=True)
        self.assertContains(
            response, "You are not authorized to delete this assignment."
        )
        self.assertTrue(Assignment.objects.filter(pk=self.assignment.pk).exists())

    def test_lecturer_can_view_submissions_list(self):
        """Allocated lecturer can view roster and submissions for their course."""
        self.client.force_login(self.lecturer1)
        url = reverse("submission_list", kwargs={"slug": self.assignment.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.assignment.title)
        self.assertContains(response, self.student1_user.username)

    def test_unallocated_lecturer_cannot_view_submissions_list(self):
        """Unallocated lecturer cannot view submissions list."""
        self.client.force_login(self.lecturer2)
        url = reverse("submission_list", kwargs={"slug": self.assignment.slug})
        response = self.client.get(url, follow=True)
        self.assertContains(
            response,
            "You are not authorized to view submissions for this assignment.",
        )

    def test_unallocated_lecturer_cannot_grade_submission(self):
        """Unallocated lecturer cannot grade submissions for other courses."""
        submission = AssignmentSubmission.objects.create(
            assignment=self.assignment,
            student=self.student1,
            file=SimpleUploadedFile("work.pdf", b"Work content"),
        )

        self.client.force_login(self.lecturer2)
        url = reverse("submission_grade", kwargs={"pk": submission.pk})
        data = {"marks": "50.00", "feedback": "Unauthorized grading"}
        response = self.client.post(url, data, follow=True)
        self.assertContains(
            response, "You are not authorized to grade this submission."
        )

        submission.refresh_from_db()
        self.assertIsNone(submission.marks)

    def test_student_cannot_grade_submission(self):
        """Students cannot access the grading endpoint."""
        submission = AssignmentSubmission.objects.create(
            assignment=self.assignment,
            student=self.student1,
            file=SimpleUploadedFile("work.pdf", b"Work content"),
        )

        self.client.force_login(self.student1_user)
        url = reverse("submission_grade", kwargs={"pk": submission.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

    # ########################################################
    # STUDENT RESUBMISSION & DOWNLOAD TESTS
    # ########################################################
    def test_student_resubmission_updates_existing_record(self):
        """When resubmission is allowed, new file submission updates the existing submission."""
        self.assignment.allow_resubmission = True
        self.assignment.save()

        # First submission
        self.client.force_login(self.student1_user)
        url = reverse("assignment_submit", kwargs={"slug": self.assignment.slug})
        first_file = SimpleUploadedFile("v1.pdf", b"Version 1 content")
        self.client.post(url, {"file": first_file, "comment": "V1"}, follow=True)

        self.assertEqual(
            AssignmentSubmission.objects.filter(assignment=self.assignment).count(), 1
        )

        # Second submission (resubmit)
        second_file = SimpleUploadedFile("v2.pdf", b"Version 2 content")
        self.client.post(url, {"file": second_file, "comment": "V2"}, follow=True)

        self.assertEqual(
            AssignmentSubmission.objects.filter(assignment=self.assignment).count(), 1
        )
        updated_sub = AssignmentSubmission.objects.get(
            assignment=self.assignment, student=self.student1
        )
        self.assertEqual(updated_sub.comment, "V2")

    def test_owner_and_allocated_lecturer_can_download_submission(self):
        """Student owner and course lecturer can download the submitted file."""
        submission = AssignmentSubmission.objects.create(
            assignment=self.assignment,
            student=self.student1,
            file=SimpleUploadedFile("my_work.pdf", b"My Work Content"),
        )

        download_url = reverse("submission_download", kwargs={"pk": submission.pk})

        # Student Owner download
        self.client.force_login(self.student1_user)
        resp_student = self.client.get(download_url)
        self.assertEqual(resp_student.status_code, 200)
        self.assertEqual(
            resp_student["Content-Disposition"],
            f'attachment; filename="{submission.file.name.split("/")[-1]}"',
        )

        # Lecturer download
        self.client.force_login(self.lecturer1)
        resp_lecturer = self.client.get(download_url)
        self.assertEqual(resp_lecturer.status_code, 200)

    # ########################################################
    # VALIDATION TESTS
    # ########################################################
    def test_assignment_form_validation_required_fields(self):
        """Assignment form requires title, due_date, and maximum_marks."""
        from .forms import AssignmentForm

        form = AssignmentForm(data={})
        self.assertFalse(form.is_valid())
        self.assertIn("title", form.errors)
        self.assertIn("due_date", form.errors)

    def test_assignment_form_validation_invalid_dates(self):
        """Assignment form rejects start_date >= due_date."""
        from .forms import AssignmentForm

        now = timezone.now()
        data = {
            "title": "Invalid Dates",
            "description": "Test",
            "start_date": (now + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M"),
            "due_date": (now + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M"),
            "maximum_marks": "50.00",
        }
        form = AssignmentForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("start_date", form.errors)

    def test_assignment_file_size_validation(self):
        """Assignment form rejects files exceeding 15MB."""
        from .forms import AssignmentForm, MAX_FILE_SIZE_BYTES

        now = timezone.now()
        oversized_content = b"0" * (MAX_FILE_SIZE_BYTES + 1024)
        large_file = SimpleUploadedFile("huge.pdf", oversized_content)

        data = {
            "title": "Big File Assignment",
            "description": "Testing large file",
            "due_date": (now + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M"),
            "maximum_marks": "50.00",
        }
        form = AssignmentForm(data=data, files={"file": large_file})
        self.assertFalse(form.is_valid())
        self.assertIn("file", form.errors)

    def test_submission_negative_marks_validation(self):
        """Submission grade form rejects negative marks."""
        from .forms import SubmissionGradeForm

        submission = AssignmentSubmission.objects.create(
            assignment=self.assignment,
            student=self.student1,
            file=SimpleUploadedFile("work.pdf", b"Work content"),
        )
        form = SubmissionGradeForm(
            data={"marks": "-5.00", "feedback": "Negative marks test"},
            assignment=self.assignment,
            instance=submission,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("marks", form.errors)

    # ########################################################
    # ADMIN INTEGRATION TESTS
    # ########################################################
    def test_admin_assignment_changelist(self):
        """Django admin assignment changelist renders properly for superuser."""
        self.client.force_login(self.admin_user)
        url = reverse("admin:assignment_assignment_changelist")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.assignment.title)

    def test_admin_submission_changelist(self):
        """Django admin submission changelist renders properly for superuser."""
        AssignmentSubmission.objects.create(
            assignment=self.assignment,
            student=self.student1,
            file=SimpleUploadedFile("work.pdf", b"Work content"),
        )

        self.client.force_login(self.admin_user)
        url = reverse("admin:assignment_assignmentsubmission_changelist")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.student1_user.username)
