"""Regression tests for authentication, account permissions, and profiles.

Covers:
- Login and logout (success and failure)
- Password hashing (never stored in plaintext)
- Role-based dashboard redirects after login
- Anonymous access restrictions (redirected to login)
- Unauthorized role changes prevented (form has no role field)
- Profile privacy (student cannot view another student's profile)
- Parent access: linked student OK, unlinked student → 403
- Duplicate parent–student relationship → IntegrityError or ValidationError
- Invalid relationship combinations → ValidationError
- seed_demo_data idempotency and production safeguard
"""
from io import StringIO

from django.contrib.auth import SESSION_KEY, get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import (
    ParentStudentRelationship,
    ParentProfile,
    Role,
    StudentProfile,
    LecturerProfile,
    RelationshipType,
)
from apps.accounts.permissions import can_view_student_data, can_edit_profile

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_user(username, email, password, role=Role.STUDENT, **extra):
    """Factory: create an active user with a hashed password."""
    return User.objects.create_user(
        username=username,
        email=email,
        password=password,
        role=role,
        **extra,
    )


# ===========================================================================
# 1. Login and Logout
# ===========================================================================

class LoginLogoutTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.student = make_user("stu1", "stu1@test.com", "testpass123", role=Role.STUDENT)
        self.login_url = reverse("accounts:login")
        self.logout_url = reverse("accounts:logout")

    def test_login_page_renders(self):
        response = self.client.get(self.login_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/login.html")

    def test_login_success_with_email(self):
        """Successful login with correct email and password."""
        response = self.client.post(
            self.login_url,
            {"email": "stu1@test.com", "password": "testpass123"},
        )
        self.assertRedirects(
            response,
            reverse("accounts:student_dashboard"),
            fetch_redirect_response=False,
        )
        self.assertIn(SESSION_KEY, self.client.session)

    def test_login_failure_wrong_password(self):
        response = self.client.post(
            self.login_url,
            {"email": "stu1@test.com", "password": "wrongpassword"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_login_failure_wrong_email(self):
        response = self.client.post(
            self.login_url,
            {"email": "nobody@test.com", "password": "testpass123"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_login_failure_inactive_user(self):
        self.student.is_active = False
        self.student.save()
        response = self.client.post(
            self.login_url,
            {"email": "stu1@test.com", "password": "testpass123"},
        )
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_authenticated_user_redirected_from_login(self):
        self.client.force_login(self.student)
        response = self.client.get(self.login_url)
        self.assertRedirects(
            response,
            reverse("accounts:student_dashboard"),
            fetch_redirect_response=False,
        )

    def test_logout_clears_session(self):
        self.client.force_login(self.student)
        response = self.client.get(self.logout_url)
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.assertRedirects(
            response,
            reverse("accounts:login"),
            fetch_redirect_response=False,
        )


# ===========================================================================
# 2. Password Hashing
# ===========================================================================

class PasswordHashingTests(TestCase):
    def test_password_is_not_stored_as_plaintext(self):
        user = make_user("hashme", "hash@test.com", "plaintext_pw")
        self.assertNotEqual(user.password, "plaintext_pw")
        self.assertFalse(user.password.startswith("plaintext"))

    def test_check_password_works(self):
        user = make_user("hashme2", "hash2@test.com", "securepass")
        self.assertTrue(user.check_password("securepass"))
        self.assertFalse(user.check_password("wrongpass"))

    def test_unusable_password_when_none_given(self):
        user = User.objects.create_user(
            username="nopass",
            email="nopass@test.com",
            password=None,
        )
        self.assertFalse(user.has_usable_password())


# ===========================================================================
# 3. Role-Based Dashboard Redirects
# ===========================================================================

class DashboardRedirectTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = make_user("adm", "adm@test.com", "pw", role=Role.ADMIN, is_staff=True)
        self.lecturer = make_user("lec", "lec@test.com", "pw", role=Role.LECTURER)
        self.student = make_user("stu", "stu@test.com", "pw", role=Role.STUDENT)
        self.parent = make_user("par", "par@test.com", "pw", role=Role.PARENT)
        self.login_url = reverse("accounts:login")

    def _login_and_get_redirect(self, email):
        return self.client.post(
            self.login_url,
            {"email": email, "password": "pw"},
        )

    def test_admin_redirected_to_admin_dashboard(self):
        response = self._login_and_get_redirect("adm@test.com")
        self.assertRedirects(
            response,
            reverse("accounts:admin_dashboard"),
            fetch_redirect_response=False,
        )

    def test_lecturer_redirected_to_lecturer_dashboard(self):
        response = self._login_and_get_redirect("lec@test.com")
        self.assertRedirects(
            response,
            reverse("accounts:lecturer_dashboard"),
            fetch_redirect_response=False,
        )

    def test_student_redirected_to_student_dashboard(self):
        response = self._login_and_get_redirect("stu@test.com")
        self.assertRedirects(
            response,
            reverse("accounts:student_dashboard"),
            fetch_redirect_response=False,
        )

    def test_parent_redirected_to_parent_dashboard(self):
        response = self._login_and_get_redirect("par@test.com")
        self.assertRedirects(
            response,
            reverse("accounts:parent_dashboard"),
            fetch_redirect_response=False,
        )


# ===========================================================================
# 4. Anonymous Access Restrictions
# ===========================================================================

class AnonymousAccessTests(TestCase):
    """All dashboard and profile routes must redirect unauthenticated users."""

    def setUp(self):
        self.client = Client()
        self.protected_urls = [
            reverse("accounts:admin_dashboard"),
            reverse("accounts:lecturer_dashboard"),
            reverse("accounts:student_dashboard"),
            reverse("accounts:parent_dashboard"),
            reverse("accounts:profile"),
            reverse("accounts:profile_edit"),
        ]

    def test_protected_routes_redirect_anonymous(self):
        for url in self.protected_urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertIn(
                    response.status_code,
                    [301, 302],
                    msg=f"{url} should redirect anonymous users",
                )
                # Ensure redirect leads to the login page
                location = response.get("Location", "")
                self.assertIn("login", location, msg=f"{url} should redirect to login")


# ===========================================================================
# 5. Role Escalation Prevention
# ===========================================================================

class RoleEscalationTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.student = make_user("stuesc", "stuesc@test.com", "pw", role=Role.STUDENT)
        self.client.force_login(self.student)

    def test_profile_update_form_has_no_role_field(self):
        from apps.accounts.forms import UserProfileUpdateForm
        form = UserProfileUpdateForm(instance=self.student)
        self.assertNotIn("role", form.fields)

    def test_post_with_role_field_does_not_change_role(self):
        """Even if a role field is smuggled in POST data, it must not be applied."""
        response = self.client.post(
            reverse("accounts:profile_edit"),
            {
                "username": self.student.username,
                "first_name": "Test",
                "last_name": "User",
                "role": Role.ADMIN,  # smuggled — must be ignored
            },
        )
        self.student.refresh_from_db()
        self.assertEqual(self.student.role, Role.STUDENT)


# ===========================================================================
# 6. Profile Privacy (IDOR Prevention)
# ===========================================================================

class ProfilePrivacyTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.student_a = make_user("stu_a", "stu_a@test.com", "pw", role=Role.STUDENT)
        self.student_b = make_user("stu_b", "stu_b@test.com", "pw", role=Role.STUDENT)

    def test_student_cannot_view_another_students_detail(self):
        """Student A tries to view Student B's profile — should get 403."""
        self.client.force_login(self.student_a)
        url = reverse("accounts:student_detail", kwargs={"student_id": self.student_b.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_student_can_view_own_profile(self):
        self.client.force_login(self.student_a)
        url = reverse("accounts:student_detail", kwargs={"student_id": self.student_a.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_lecturer_cannot_view_student_detail(self):
        lec = make_user("lec_p", "lec_p@test.com", "pw", role=Role.LECTURER)
        self.client.force_login(lec)
        url = reverse("accounts:student_detail", kwargs={"student_id": self.student_a.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_can_view_student_data_helper(self):
        admin = make_user("adm_p", "adm_p@test.com", "pw", role=Role.ADMIN, is_staff=True)
        self.assertTrue(can_view_student_data(admin, self.student_a))
        self.assertTrue(can_view_student_data(self.student_a, self.student_a))
        self.assertFalse(can_view_student_data(self.student_b, self.student_a))

    def test_can_edit_profile_helper(self):
        self.assertTrue(can_edit_profile(self.student_a, self.student_a))
        self.assertFalse(can_edit_profile(self.student_b, self.student_a))


# ===========================================================================
# 7. Parent Access to Student Data
# ===========================================================================

class ParentAccessTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.parent = make_user("par_acc", "par_acc@test.com", "pw", role=Role.PARENT)
        self.linked_student = make_user("stu_linked", "stu_linked@test.com", "pw", role=Role.STUDENT)
        self.unlinked_student = make_user("stu_unlinked", "stu_unlinked@test.com", "pw", role=Role.STUDENT)
        # Link parent → linked_student
        ParentStudentRelationship.objects.create(
            parent=self.parent,
            student=self.linked_student,
            relationship_type=RelationshipType.GUARDIAN,
        )

    def test_parent_can_view_linked_student(self):
        self.client.force_login(self.parent)
        url = reverse("accounts:student_detail", kwargs={"student_id": self.linked_student.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_parent_cannot_view_unlinked_student(self):
        self.client.force_login(self.parent)
        url = reverse("accounts:student_detail", kwargs={"student_id": self.unlinked_student.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_parent_cannot_access_admin_dashboard(self):
        self.client.force_login(self.parent)
        response = self.client.get(reverse("accounts:admin_dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_parent_cannot_access_student_dashboard(self):
        self.client.force_login(self.parent)
        response = self.client.get(reverse("accounts:student_dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_can_view_student_data_linked_parent(self):
        self.assertTrue(can_view_student_data(self.parent, self.linked_student))
        self.assertFalse(can_view_student_data(self.parent, self.unlinked_student))


# ===========================================================================
# 8. Parent–Student Relationship Validation
# ===========================================================================

class RelationshipValidationTests(TestCase):
    def setUp(self):
        self.parent = make_user("par_rel", "par_rel@test.com", "pw", role=Role.PARENT)
        self.student = make_user("stu_rel", "stu_rel@test.com", "pw", role=Role.STUDENT)

    def test_duplicate_relationship_raises_integrity_error(self):
        ParentStudentRelationship.objects.create(
            parent=self.parent,
            student=self.student,
        )
        with self.assertRaises(IntegrityError):
            ParentStudentRelationship.objects.create(
                parent=self.parent,
                student=self.student,
            )

    def test_same_user_as_parent_and_student_raises_validation_error(self):
        """A user cannot be linked to themselves."""
        rel = ParentStudentRelationship(
            parent=self.parent,
            student=self.parent,  # same user — invalid
        )
        with self.assertRaises(ValidationError):
            rel.clean()

    def test_non_parent_role_raises_validation_error(self):
        """The 'parent' must have the PARENT role."""
        non_parent = make_user("lec_np", "lec_np@test.com", "pw", role=Role.LECTURER)
        rel = ParentStudentRelationship(
            parent=non_parent,
            student=self.student,
        )
        with self.assertRaises(ValidationError):
            rel.clean()

    def test_non_student_role_raises_validation_error(self):
        """The 'student' must have the STUDENT role."""
        non_student = make_user("par_ns", "par_ns@test.com", "pw", role=Role.PARENT)
        rel = ParentStudentRelationship(
            parent=self.parent,
            student=non_student,
        )
        with self.assertRaises(ValidationError):
            rel.clean()

    def test_valid_relationship_passes_clean(self):
        rel = ParentStudentRelationship(
            parent=self.parent,
            student=self.student,
            relationship_type=RelationshipType.MOTHER,
        )
        rel.clean()  # Should not raise


# ===========================================================================
# 9. Admin-Only Relationship Management Routes
# ===========================================================================

class AdminRelationshipRouteTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = make_user("adm_rel", "adm_rel@test.com", "pw", role=Role.ADMIN, is_staff=True)
        self.student_user = make_user("stu_r", "stu_r@test.com", "pw", role=Role.STUDENT)
        self.list_url = reverse("accounts:admin_relationship_list")
        self.create_url = reverse("accounts:admin_relationship_create")

    def test_student_cannot_access_relationship_list(self):
        self.client.force_login(self.student_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 403)

    def test_admin_can_access_relationship_list(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)

    def test_admin_can_access_relationship_create(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.create_url)
        self.assertEqual(response.status_code, 200)


# ===========================================================================
# 10. Access-Denied View
# ===========================================================================

class AccessDeniedViewTests(TestCase):
    def test_access_denied_page_returns_403(self):
        response = self.client.get(reverse("accounts:access_denied"))
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, "accounts/access_denied.html")


# ===========================================================================
# 11. seed_demo_data Management Command
# ===========================================================================

class SeedDemoDataTests(TestCase):
    def _call_seed(self):
        """Run seed_demo_data command with DEBUG=True and return stdout."""
        from django.core.management import call_command
        out = StringIO()
        # Django test runner always sets DEBUG=False; override it for seed tests
        with self.settings(DEBUG=True):
            call_command("seed_demo_data", stdout=out)
        return out.getvalue()

    @override_settings(DEBUG=True)
    def test_seed_creates_demo_accounts(self):
        self._call_seed()
        self.assertEqual(
            set(User.objects.filter(email__endswith="@example.com").values_list("email", flat=True)),
            {"student1@example.com", "lecturer1@example.com", "admin1@example.com", "parent1@example.com"},
        )
        student = User.objects.get(email="student1@example.com")
        self.assertEqual(student.get_full_name, "Student 1")
        self.assertEqual(student.get_short_name, "Student 1")

    @override_settings(DEBUG=True)
    def test_seed_idempotent_second_run(self):
        """Running seed twice should not duplicate accounts."""
        self._call_seed()
        self._call_seed()
        self.assertEqual(User.objects.filter(email="student1@example.com").count(), 1)

    @override_settings(DEBUG=True)
    def test_seed_creates_parent_student_relationship(self):
        self._call_seed()
        parent = User.objects.get(email="parent1@example.com")
        student = User.objects.get(email="student1@example.com")
        self.assertTrue(
            ParentStudentRelationship.objects.filter(
                parent=parent, student=student
            ).exists()
        )

    @override_settings(DEBUG=True)
    def test_seed_assigns_correct_roles(self):
        self._call_seed()
        self.assertEqual(User.objects.get(email="student1@example.com").role, Role.STUDENT)
        self.assertEqual(User.objects.get(email="lecturer1@example.com").role, Role.LECTURER)
        self.assertEqual(User.objects.get(email="admin1@example.com").role, Role.ADMIN)
        self.assertEqual(User.objects.get(email="parent1@example.com").role, Role.PARENT)

    @override_settings(DEBUG=True)
    def test_seed_demo_passwords_are_hashed(self):
        self._call_seed()
        student = User.objects.get(email="student1@example.com")
        self.assertTrue(student.check_password("password"))
        self.assertNotEqual(student.password, "password")

    @override_settings(DEBUG=False)
    def test_seed_refuses_in_production(self):
        """Seed command must raise CommandError when DEBUG=False."""
        from django.core.management import call_command
        from django.core.management.base import CommandError
        out = StringIO()
        with self.assertRaises(CommandError):
            call_command("seed_demo_data", stdout=out)
        # Demo accounts must NOT be created
        self.assertFalse(User.objects.filter(email="student1@example.com").exists())

    @override_settings(DEBUG=True, ENVIRONMENT="production")
    def test_seed_refuses_production_environment_even_if_debug_is_enabled(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            call_command("seed_demo_data", stdout=StringIO())

    @override_settings(DEBUG=True)
    def test_seed_anonymizes_legacy_accounts_in_place(self):
        from django.core.management import call_command

        student = make_user(
            "student123", "legacy-student@example.test", "old-password",
            role=Role.STUDENT, first_name="Private", last_name="Student",
        )
        student_profile = StudentProfile.objects.create(
            user=student, student_id="LEGACY-STUDENT", program="Existing program",
            phone="555-0101", emergency_contact="Private contact",
        )
        parent = make_user(
            "parent123", "legacy-parent@example.test", "old-password",
            role=Role.PARENT, first_name="Private", last_name="Parent",
        )
        parent_profile = ParentProfile.objects.create(
            user=parent, phone="555-0102", address="Private address",
        )
        relationship = ParentStudentRelationship.objects.create(
            parent=parent, student=student, relationship_type=RelationshipType.MOTHER,
        )
        relationship_id = relationship.pk
        student_profile_id = student_profile.pk
        parent_profile_id = parent_profile.pk

        call_command("seed_demo_data", stdout=StringIO())
        student.refresh_from_db()
        parent.refresh_from_db()
        student_profile.refresh_from_db()
        parent_profile.refresh_from_db()
        relationship.refresh_from_db()

        self.assertEqual(student_profile.pk, student_profile_id)
        self.assertEqual(parent_profile.pk, parent_profile_id)
        self.assertEqual(student.pk, student_profile.user_id)
        self.assertEqual(
            (student.username, student.email, student.get_full_name),
            ("student1", "student1@example.com", "Student 1"),
        )
        self.assertEqual(student_profile.program, "Existing program")
        self.assertEqual((student_profile.phone, student_profile.emergency_contact), ("", ""))
        self.assertEqual(
            (parent.username, parent.email, parent.get_full_name),
            ("parent1", "parent1@example.com", "Parent 1"),
        )
        self.assertEqual((parent_profile.phone, parent_profile.address), ("", ""))
        self.assertEqual(relationship.pk, relationship_id)
        self.assertEqual(relationship.relationship_type, RelationshipType.MOTHER)

    @override_settings(DEBUG=True)
    def test_seed_aborts_on_ambiguous_legacy_and_canonical_accounts(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError

        make_user("student123", "old-student@example.test", "pw", role=Role.STUDENT)
        make_user("student1", "student1@example.com", "pw", role=Role.STUDENT)
        with self.assertRaises(CommandError):
            call_command("seed_demo_data", stdout=StringIO())


# ===========================================================================
# 12. User Model Properties
# ===========================================================================

class UserModelPropertyTests(TestCase):
    def test_is_admin_role(self):
        admin = make_user("adm_prop", "adm_prop@test.com", "pw", role=Role.ADMIN, is_staff=True)
        self.assertTrue(admin.is_admin_role)

    def test_is_lecturer_role(self):
        lec = make_user("lec_prop", "lec_prop@test.com", "pw", role=Role.LECTURER)
        self.assertTrue(lec.is_lecturer_role)
        self.assertFalse(lec.is_student_role)

    def test_is_student_role(self):
        stu = make_user("stu_prop", "stu_prop@test.com", "pw", role=Role.STUDENT)
        self.assertTrue(stu.is_student_role)

    def test_is_parent_role(self):
        par = make_user("par_prop", "par_prop@test.com", "pw", role=Role.PARENT)
        self.assertTrue(par.is_parent_role)

    def test_get_full_name_with_names(self):
        stu = make_user("fn_stu", "fn@test.com", "pw", first_name="Alice", last_name="Smith")
        self.assertEqual(stu.get_full_name, "Alice Smith")

    def test_get_full_name_fallback_to_username(self):
        stu = make_user("fn_stu2", "fn2@test.com", "pw")
        self.assertEqual(stu.get_full_name, "fn_stu2")

    def test_superuser_forced_to_admin_role(self):
        su = make_user("superu", "su@test.com", "pw", is_superuser=True, is_staff=True)
        su.clean()
        self.assertEqual(su.role, Role.ADMIN)
