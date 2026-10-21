"""Regression coverage for Django admin branding and ordinary workflows."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.academics.models import Department


User = get_user_model()


class AdminExperienceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(
            username="admin-ui-test",
            email="admin-ui-test@example.test",
            password="test-password",
        )

    def test_login_and_index_use_admin_theme(self):
        login = self.client.get(reverse("admin:login"))
        self.assertEqual(login.status_code, 200)
        self.assertContains(login, "css/admin.css")

        self.client.force_login(self.admin)
        index = self.client.get(reverse("admin:index"))
        self.assertEqual(index.status_code, 200)
        self.assertContains(index, "css/admin.css")
        self.assertContains(index, "Academic LMS Administration")

    def test_non_staff_user_cannot_open_admin(self):
        student = User.objects.create_user(
            username="student-ui-test",
            email="student-ui-test@example.test",
            password="test-password",
        )
        self.client.force_login(student)
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("admin:login"), response["Location"])

    def test_department_admin_search_and_create_work(self):
        self.client.force_login(self.admin)
        changelist = reverse("admin:academics_department_changelist")
        response = self.client.get(changelist, {"q": "CS-TEST"})
        self.assertEqual(response.status_code, 200)

        add_response = self.client.post(
            reverse("admin:academics_department_add"),
            {
                "name": "Computer Science Test Department",
                "code": "CS-TEST",
                "description": "Admin workflow test",
                "is_active": "on",
                "_save": "Save",
            },
        )
        self.assertEqual(add_response.status_code, 302)
        self.assertTrue(Department.objects.filter(code="CS-TEST").exists())
