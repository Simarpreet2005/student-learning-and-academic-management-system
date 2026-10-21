"""Automated test suite for Courseware & Digital Learning Materials.

Comprehensive test coverage across:
- Model validation, safe storage naming, and resource constraints
- Role-based permissions: Admin, Lecturer, Student, Parent
- Scoping rules: allocated vs unallocated, enrolled vs non-enrolled, linked vs unlinked
- Draft vs published visibility
- Secure file delivery & permission-checked downloads
- File type (allowed vs prohibited) and size validation
- Search, filtering, and pagination
"""
import io
from django.core.exceptions import ValidationError, PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import (
    User,
    Role,
    StudentProfile,
    LecturerProfile,
    ParentProfile,
    ParentStudentRelationship,
    RelationshipType,
)
from apps.academics.models import (
    Department,
    AcademicYear,
    Semester,
    Course,
    CourseAllocation,
    StudentEnrollment,
    EnrollmentStatus,
)
from apps.courseware.models import (
    CourseModule,
    LearningResource,
    ResourceType,
    ResourceStatus,
)
from apps.courseware.validators import (
    resource_upload_path,
    validate_resource_file,
    validate_resource_url,
)
from apps.courseware.permissions import (
    can_view_resource,
    can_manage_resource,
    can_download_resource,
    get_accessible_resources_queryset,
)


class CoursewareBaseTestCase(TestCase):
    """Base test fixture setting up users across all 4 roles, courses, allocations, and enrollments."""

    def setUp(self):
        # 1. Users
        self.admin_user = User.objects.create_superuser(
            email="admin@test.com",
            username="admin_user",
            password="Password123!",
        )

        self.lecturer_1 = User.objects.create_user(
            email="prof_smith@test.com",
            username="prof_smith",
            password="Password123!",
            role=Role.LECTURER,
        )
        LecturerProfile.objects.create(user=self.lecturer_1, employee_id="LEC-001")

        self.lecturer_2 = User.objects.create_user(
            email="prof_jones@test.com",
            username="prof_jones",
            password="Password123!",
            role=Role.LECTURER,
        )
        LecturerProfile.objects.create(user=self.lecturer_2, employee_id="LEC-002")

        self.student_1 = User.objects.create_user(
            email="alice@test.com",
            username="alice_student",
            password="Password123!",
            role=Role.STUDENT,
        )
        StudentProfile.objects.create(user=self.student_1, student_id="STD-001")

        self.student_2 = User.objects.create_user(
            email="bob@test.com",
            username="bob_student",
            password="Password123!",
            role=Role.STUDENT,
        )
        StudentProfile.objects.create(user=self.student_2, student_id="STD-002")

        self.parent_alice = User.objects.create_user(
            email="parent_alice@test.com",
            username="parent_alice",
            password="Password123!",
            role=Role.PARENT,
        )
        ParentProfile.objects.create(user=self.parent_alice)

        self.parent_other = User.objects.create_user(
            email="parent_other@test.com",
            username="parent_other",
            password="Password123!",
            role=Role.PARENT,
        )
        ParentProfile.objects.create(user=self.parent_other)

        # Link parent_alice -> student_1 (Alice)
        ParentStudentRelationship.objects.create(
            parent=self.parent_alice,
            student=self.student_1,
            relationship_type=RelationshipType.MOTHER,
        )

        # 2. Academic Entities
        self.dept = Department.objects.create(name="Computer Science", code="CS")
        self.year = AcademicYear.objects.create(
            name="2026/2027",
            start_date=timezone.now().date(),
            end_date=timezone.now().date() + timezone.timedelta(days=365),
            is_current=True,
        )
        self.semester = Semester.objects.create(
            academic_year=self.year,
            name="Fall 2026",
            start_date=timezone.now().date(),
            end_date=timezone.now().date() + timezone.timedelta(days=120),
        )

        # Course 1: CS101 (Allocated to Lecturer 1; Enrolled by Student 1 Alice)
        self.course_1 = Course.objects.create(
            code="CS101",
            title="Introduction to Programming",
            department=self.dept,
            credits=3,
        )
        CourseAllocation.objects.create(
            course=self.course_1,
            lecturer=self.lecturer_1,
            semester=self.semester,
        )
        StudentEnrollment.objects.create(
            course=self.course_1,
            student=self.student_1,
            semester=self.semester,
            status=EnrollmentStatus.ENROLLED,
        )

        # Course 2: CS202 (Allocated to Lecturer 2; Enrolled by Student 2 Bob)
        self.course_2 = Course.objects.create(
            code="CS202",
            title="Data Structures & Algorithms",
            department=self.dept,
            credits=4,
        )
        CourseAllocation.objects.create(
            course=self.course_2,
            lecturer=self.lecturer_2,
            semester=self.semester,
        )
        StudentEnrollment.objects.create(
            course=self.course_2,
            student=self.student_2,
            semester=self.semester,
            status=EnrollmentStatus.ENROLLED,
        )

        # 3. Topic Modules
        self.module_1 = CourseModule.objects.create(
            course=self.course_1,
            title="Week 1: Python Fundamentals",
            order=1,
        )

        # 4. Resources for Course 1
        self.sample_pdf = SimpleUploadedFile("lecture1.pdf", b"%PDF-1.4 sample content", content_type="application/pdf")
        self.resource_published_file = LearningResource.objects.create(
            course=self.course_1,
            module=self.module_1,
            title="Lecture 1 Notes",
            description="Introduction to syntax and variables",
            resource_type=ResourceType.DOCUMENT,
            status=ResourceStatus.PUBLISHED,
            file=self.sample_pdf,
            original_filename="lecture1.pdf",
            file_size=len(b"%PDF-1.4 sample content"),
            created_by=self.lecturer_1,
        )

        self.resource_draft = LearningResource.objects.create(
            course=self.course_1,
            module=self.module_1,
            title="Upcoming Quiz Study Guide",
            description="Draft notes under review",
            resource_type=ResourceType.DOCUMENT,
            status=ResourceStatus.DRAFT,
            external_url="https://example.com/guide",
            created_by=self.lecturer_1,
        )

        self.resource_link = LearningResource.objects.create(
            course=self.course_1,
            title="Official Python Tutorial",
            description="Reference documentation",
            resource_type=ResourceType.EXTERNAL_LINK,
            status=ResourceStatus.PUBLISHED,
            external_url="https://docs.python.org/3/",
            created_by=self.lecturer_1,
        )

        # Resource for Course 2
        self.resource_course_2 = LearningResource.objects.create(
            course=self.course_2,
            title="CS202 Syllabus",
            description="Course policies and schedule",
            resource_type=ResourceType.DOCUMENT,
            status=ResourceStatus.PUBLISHED,
            external_url="https://example.com/cs202",
            created_by=self.lecturer_2,
        )


class LearningResourceModelTests(CoursewareBaseTestCase):
    """Test model validation, custom upload paths, properties, and constraints."""

    def test_resource_string_representation(self):
        self.assertIn("CS101", str(self.resource_published_file))
        self.assertIn("Lecture 1 Notes", str(self.resource_published_file))

    def test_is_published_property(self):
        self.assertTrue(self.resource_published_file.is_published)
        self.assertFalse(self.resource_draft.is_published)

        # Soft deactivated resource is not published
        self.resource_published_file.is_active = False
        self.assertFalse(self.resource_published_file.is_published)

    def test_safe_upload_path_generation(self):
        safe_path = resource_upload_path(self.resource_published_file, "malicious/../../../path/test.PDF")
        self.assertTrue(safe_path.startswith("courseware/cs101/"))
        self.assertTrue(safe_path.endswith(".pdf"))
        self.assertNotIn("..", safe_path)
        self.assertNotIn("malicious", safe_path)

    def test_link_resource_requires_external_url(self):
        resource = LearningResource(
            course=self.course_1,
            title="Missing URL Link",
            resource_type=ResourceType.EXTERNAL_LINK,
            created_by=self.lecturer_1,
        )
        with self.assertRaises(ValidationError):
            resource.clean()

    def test_document_requires_file_or_url(self):
        resource = LearningResource(
            course=self.course_1,
            title="Empty Document",
            resource_type=ResourceType.DOCUMENT,
            created_by=self.lecturer_1,
        )
        with self.assertRaises(ValidationError):
            resource.clean()

    def test_module_must_belong_to_same_course(self):
        # Module 1 belongs to Course 1; try attaching it to Course 2
        resource = LearningResource(
            course=self.course_2,
            module=self.module_1,
            title="Cross-course Module Resource",
            resource_type=ResourceType.EXTERNAL_LINK,
            external_url="https://example.com",
            created_by=self.lecturer_2,
        )
        with self.assertRaises(ValidationError):
            resource.clean()

    def test_dangerous_executable_extensions_rejected(self):
        bad_file = SimpleUploadedFile("script.py", b"print('exploit')", content_type="text/x-python")
        with self.assertRaises(ValidationError):
            validate_resource_file(bad_file)

        exe_file = SimpleUploadedFile("setup.exe", b"MZbinary", content_type="application/octet-stream")
        with self.assertRaises(ValidationError):
            validate_resource_file(exe_file)

    def test_allowed_extensions_pass_validation(self):
        valid_pdf = SimpleUploadedFile("doc.pdf", b"test pdf", content_type="application/pdf")
        valid_docx = SimpleUploadedFile("notes.docx", b"test docx", content_type="application/vnd.openxmlformats")
        # Should not raise
        validate_resource_file(valid_pdf)
        validate_resource_file(valid_docx)

    def test_max_file_size_exceeded_raises_validation_error(self):
        # Simulate oversized file
        fake_large_file = SimpleUploadedFile("big.pdf", b"1", content_type="application/pdf")
        fake_large_file.size = 25 * 1024 * 1024  # 25 MB > 20 MB default limit
        with self.assertRaises(ValidationError):
            validate_resource_file(fake_large_file)

    def test_unsafe_url_schemes_rejected(self):
        with self.assertRaises(ValidationError):
            validate_resource_url("javascript:alert(1)")
        with self.assertRaises(ValidationError):
            validate_resource_url("data:text/html;base64,PHNjcmlwdD4=")
        with self.assertRaises(ValidationError):
            validate_resource_url("file:///etc/passwd")

    def test_safe_http_and_https_urls_accepted(self):
        # Should not raise
        validate_resource_url("https://stanford.edu/cs101/notes.html")
        validate_resource_url("http://ocw.mit.edu/courses")


class LecturerPermissionsTests(CoursewareBaseTestCase):
    """Test lecturer authorization across allocated vs unallocated courses."""

    def test_lecturer_sees_only_allocated_courses_in_list(self):
        self.client.force_login(self.lecturer_1)
        response = self.client.get(reverse("courseware:resource_list"))
        self.assertEqual(response.status_code, 200)

        # Lecturer 1 should see resources for Course 1
        self.assertContains(response, "Lecture 1 Notes")
        self.assertContains(response, "Official Python Tutorial")
        # Lecturer 1 should ALSO see draft resources of their allocated course
        self.assertContains(response, "Upcoming Quiz Study Guide")
        # Lecturer 1 must NOT see resources for Course 2 (unallocated)
        self.assertNotContains(response, "CS202 Syllabus")

    def test_lecturer_can_view_detail_of_allocated_resource(self):
        self.client.force_login(self.lecturer_1)
        response = self.client.get(reverse("courseware:resource_detail", kwargs={"pk": self.resource_published_file.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Lecture 1 Notes")

    def test_lecturer_cannot_view_resource_of_unallocated_course(self):
        self.client.force_login(self.lecturer_1)
        # Attempt to access Course 2 resource allocated to Lecturer 2
        response = self.client.get(reverse("courseware:resource_detail", kwargs={"pk": self.resource_course_2.pk}))
        self.assertEqual(response.status_code, 403)

    def test_lecturer_can_create_resource_for_allocated_course(self):
        self.client.force_login(self.lecturer_1)
        post_data = {
            "course": self.course_1.pk,
            "title": "Week 2 Lecture Notes",
            "description": "Functions and modules",
            "resource_type": ResourceType.EXTERNAL_LINK,
            "status": ResourceStatus.PUBLISHED,
            "external_url": "https://example.com/week2",
        }
        response = self.client.post(reverse("courseware:resource_create"), data=post_data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(LearningResource.objects.filter(title="Week 2 Lecture Notes").exists())

    def test_lecturer_cannot_create_resource_for_unallocated_course(self):
        self.client.force_login(self.lecturer_1)
        # Attempt to post for Course 2 (unallocated)
        post_data = {
            "course": self.course_2.pk,
            "title": "Unauthorized Lecture",
            "resource_type": ResourceType.EXTERNAL_LINK,
            "status": ResourceStatus.PUBLISHED,
            "external_url": "https://example.com/unauthorized",
        }
        response = self.client.post(reverse("courseware:resource_create"), data=post_data)
        # Form validation rejects unallocated course
        self.assertFalse(LearningResource.objects.filter(title="Unauthorized Lecture").exists())

    def test_lecturer_can_edit_allocated_resource(self):
        self.client.force_login(self.lecturer_1)
        post_data = {
            "course": self.course_1.pk,
            "title": "Lecture 1 Notes (Updated)",
            "description": "Updated syntax guide",
            "resource_type": ResourceType.EXTERNAL_LINK,
            "status": ResourceStatus.PUBLISHED,
            "external_url": "https://example.com/updated",
        }
        response = self.client.post(
            reverse("courseware:resource_edit", kwargs={"pk": self.resource_published_file.pk}),
            data=post_data,
        )
        self.assertEqual(response.status_code, 302)
        self.resource_published_file.refresh_from_db()
        self.assertEqual(self.resource_published_file.title, "Lecture 1 Notes (Updated)")

    def test_lecturer_cannot_edit_unallocated_resource(self):
        self.client.force_login(self.lecturer_1)
        response = self.client.get(reverse("courseware:resource_edit", kwargs={"pk": self.resource_course_2.pk}))
        self.assertEqual(response.status_code, 403)

    def test_lecturer_can_deactivate_allocated_resource(self):
        self.client.force_login(self.lecturer_1)
        response = self.client.post(reverse("courseware:resource_delete", kwargs={"pk": self.resource_draft.pk}))
        self.assertEqual(response.status_code, 302)
        self.resource_draft.refresh_from_db()
        self.assertFalse(self.resource_draft.is_active)


class StudentPermissionsTests(CoursewareBaseTestCase):
    """Test student access: enrolled courses only, published resources only, zero management rights."""

    def test_student_sees_only_published_materials_for_enrolled_courses(self):
        self.client.force_login(self.student_1)
        response = self.client.get(reverse("courseware:resource_list"))
        self.assertEqual(response.status_code, 200)

        # Enrolled Course 1 published resources should be visible
        self.assertContains(response, "Lecture 1 Notes")
        self.assertContains(response, "Official Python Tutorial")

        # Draft resource in enrolled course MUST NOT be visible to student
        self.assertNotContains(response, "Upcoming Quiz Study Guide")

        # Unenrolled Course 2 resources MUST NOT be visible to student 1
        self.assertNotContains(response, "CS202 Syllabus")

    def test_student_cannot_view_draft_resource_detail(self):
        self.client.force_login(self.student_1)
        response = self.client.get(reverse("courseware:resource_detail", kwargs={"pk": self.resource_draft.pk}))
        self.assertEqual(response.status_code, 403)

    def test_student_cannot_view_unenrolled_course_resource_detail(self):
        self.client.force_login(self.student_1)
        response = self.client.get(reverse("courseware:resource_detail", kwargs={"pk": self.resource_course_2.pk}))
        self.assertEqual(response.status_code, 403)

    def test_student_cannot_access_create_page(self):
        self.client.force_login(self.student_1)
        response = self.client.get(reverse("courseware:resource_create"))
        self.assertEqual(response.status_code, 403)

    def test_student_cannot_access_edit_page(self):
        self.client.force_login(self.student_1)
        response = self.client.get(reverse("courseware:resource_edit", kwargs={"pk": self.resource_published_file.pk}))
        self.assertEqual(response.status_code, 403)

    def test_student_cannot_access_delete_page(self):
        self.client.force_login(self.student_1)
        response = self.client.get(reverse("courseware:resource_delete", kwargs={"pk": self.resource_published_file.pk}))
        self.assertEqual(response.status_code, 403)


class ParentPermissionsTests(CoursewareBaseTestCase):
    """Test parent access: linked student courses only, published resources only, strictly read-only."""

    def test_parent_sees_materials_for_linked_student_enrolled_courses(self):
        self.client.force_login(self.parent_alice)
        response = self.client.get(reverse("courseware:resource_list"))
        self.assertEqual(response.status_code, 200)

        # Alice is enrolled in Course 1: published materials must be visible
        self.assertContains(response, "Lecture 1 Notes")
        self.assertContains(response, "Official Python Tutorial")

        # Drafts must NOT be visible
        self.assertNotContains(response, "Upcoming Quiz Study Guide")

        # Alice is NOT enrolled in Course 2: Course 2 materials must NOT be visible
        self.assertNotContains(response, "CS202 Syllabus")

    def test_parent_with_no_linked_students_sees_empty_list(self):
        self.client.force_login(self.parent_other)
        response = self.client.get(reverse("courseware:resource_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No Learning Materials Found")
        self.assertNotContains(response, "Lecture 1 Notes")

    def test_parent_cannot_view_unrelated_course_resource(self):
        self.client.force_login(self.parent_alice)
        # Attempt to access Course 2 resource (Bob's course, not Alice's)
        response = self.client.get(reverse("courseware:resource_detail", kwargs={"pk": self.resource_course_2.pk}))
        self.assertEqual(response.status_code, 403)

    def test_parent_cannot_create_or_edit_resources(self):
        self.client.force_login(self.parent_alice)
        response_create = self.client.get(reverse("courseware:resource_create"))
        self.assertEqual(response_create.status_code, 403)

        response_edit = self.client.get(reverse("courseware:resource_edit", kwargs={"pk": self.resource_published_file.pk}))
        self.assertEqual(response_edit.status_code, 403)


class AdminPermissionsTests(CoursewareBaseTestCase):
    """Test administrator institutional oversight."""

    def test_admin_can_view_all_resources_including_drafts(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse("courseware:resource_list"))
        self.assertEqual(response.status_code, 200)

        # Admin sees all courses and all statuses
        self.assertContains(response, "Lecture 1 Notes")
        self.assertContains(response, "Upcoming Quiz Study Guide")
        self.assertContains(response, "CS202 Syllabus")

    def test_admin_can_create_resource_for_any_course(self):
        self.client.force_login(self.admin_user)
        post_data = {
            "course": self.course_2.pk,
            "title": "Admin Posted Guide",
            "resource_type": ResourceType.EXTERNAL_LINK,
            "status": ResourceStatus.PUBLISHED,
            "external_url": "https://example.com/admin-guide",
        }
        response = self.client.post(reverse("courseware:resource_create"), data=post_data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(LearningResource.objects.filter(title="Admin Posted Guide").exists())


class SecureDownloadTests(CoursewareBaseTestCase):
    """Test permission-enforced file downloading and protection against unauthorized direct access."""

    def test_anonymous_user_redirected_to_login(self):
        response = self.client.get(reverse("courseware:resource_download", kwargs={"pk": self.resource_published_file.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_enrolled_student_can_download_published_file(self):
        self.client.force_login(self.student_1)
        response = self.client.get(reverse("courseware:resource_download", kwargs={"pk": self.resource_published_file.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn("lecture1.pdf", response["Content-Disposition"])

    def test_unenrolled_student_denied_download(self):
        # Student 2 is NOT enrolled in Course 1
        self.client.force_login(self.student_2)
        response = self.client.get(reverse("courseware:resource_download", kwargs={"pk": self.resource_published_file.pk}))
        self.assertEqual(response.status_code, 403)

    def test_student_cannot_download_draft_file(self):
        # Create a draft with an attached file
        draft_pdf = SimpleUploadedFile("draft.pdf", b"%PDF draft", content_type="application/pdf")
        draft_resource = LearningResource.objects.create(
            course=self.course_1,
            title="Draft File",
            resource_type=ResourceType.DOCUMENT,
            status=ResourceStatus.DRAFT,
            file=draft_pdf,
            original_filename="draft.pdf",
            created_by=self.lecturer_1,
        )

        self.client.force_login(self.student_1)
        response = self.client.get(reverse("courseware:resource_download", kwargs={"pk": draft_resource.pk}))
        self.assertEqual(response.status_code, 403)

    def test_allocated_lecturer_can_download_draft_file(self):
        draft_pdf = SimpleUploadedFile("draft.pdf", b"%PDF draft", content_type="application/pdf")
        draft_resource = LearningResource.objects.create(
            course=self.course_1,
            title="Draft File",
            resource_type=ResourceType.DOCUMENT,
            status=ResourceStatus.DRAFT,
            file=draft_pdf,
            original_filename="draft.pdf",
            created_by=self.lecturer_1,
        )

        self.client.force_login(self.lecturer_1)
        response = self.client.get(reverse("courseware:resource_download", kwargs={"pk": draft_resource.pk}))
        self.assertEqual(response.status_code, 200)

    def test_unallocated_lecturer_denied_download(self):
        self.client.force_login(self.lecturer_2)
        response = self.client.get(reverse("courseware:resource_download", kwargs={"pk": self.resource_published_file.pk}))
        self.assertEqual(response.status_code, 403)

    def test_linked_parent_can_download_published_file(self):
        self.client.force_login(self.parent_alice)
        response = self.client.get(reverse("courseware:resource_download", kwargs={"pk": self.resource_published_file.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])

    def test_unlinked_parent_denied_download(self):
        self.client.force_login(self.parent_other)
        response = self.client.get(reverse("courseware:resource_download", kwargs={"pk": self.resource_published_file.pk}))
        self.assertEqual(response.status_code, 403)

    def test_deactivated_resource_download_returns_404(self):
        self.resource_published_file.is_active = False
        self.resource_published_file.save()

        self.client.force_login(self.student_1)
        response = self.client.get(reverse("courseware:resource_download", kwargs={"pk": self.resource_published_file.pk}))
        self.assertEqual(response.status_code, 404)


class SearchAndFilterTests(CoursewareBaseTestCase):
    """Test search querying, course filtering, type filtering, and pagination."""

    def test_search_by_title_and_description(self):
        self.client.force_login(self.admin_user)

        response = self.client.get(reverse("courseware:resource_list"), {"q": "Python"})
        self.assertContains(response, "Official Python Tutorial")
        self.assertNotContains(response, "CS202 Syllabus")

        response_code = self.client.get(reverse("courseware:resource_list"), {"q": "CS202"})
        self.assertContains(response_code, "CS202 Syllabus")
        self.assertNotContains(response_code, "Lecture 1 Notes")

    def test_filter_by_course(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse("courseware:resource_list"), {"course": "CS101"})
        self.assertContains(response, "Lecture 1 Notes")
        self.assertNotContains(response, "CS202 Syllabus")

    def test_filter_by_resource_type(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse("courseware:resource_list"), {"type": ResourceType.EXTERNAL_LINK})
        self.assertContains(response, "Official Python Tutorial")
        self.assertNotContains(response, "Lecture 1 Notes")

    def test_pagination_renders_when_exceeding_page_size(self):
        # Create 15 dummy resources
        for i in range(15):
            LearningResource.objects.create(
                course=self.course_1,
                title=f"Batch Resource {i}",
                resource_type=ResourceType.EXTERNAL_LINK,
                status=ResourceStatus.PUBLISHED,
                external_url=f"https://example.com/res-{i}",
                created_by=self.lecturer_1,
            )

        self.client.force_login(self.admin_user)
        response = self.client.get(reverse("courseware:resource_list"))
        self.assertTrue(response.context["is_paginated"])
        self.assertContains(response, "Next &raquo;")
