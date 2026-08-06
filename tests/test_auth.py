"""Functional tests for registration, login, logout and lockout (FR-1, FR-2)."""

from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.forms import AdminUserForm, StudentSignUpForm
from accounts.models import AuditAction, AuditLog, Role, User

from .factories import PASSWORD, make_admin, make_department, make_hod, make_student


class RegistrationTests(TestCase):
    def setUp(self):
        self.department = make_department()
        self.url = reverse("accounts:signup")

    def _payload(self, **overrides):
        payload = {
            "full_name": "New Student",
            "email": "new.student@test.local",
            "identifier": "BSIT-22-999999",
            "phone": "0300-1234567",
            "department": self.department.pk,
            "password1": "Str0ng!Portal2026",
            "password2": "Str0ng!Portal2026",
            "accept_terms": "on",
        }
        payload.update(overrides)
        return payload

    def test_signup_page_renders(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create a student account")

    def test_valid_registration_creates_student(self):
        response = self.client.post(self.url, self._payload())
        self.assertRedirects(response, reverse("accounts:login"))
        user = User.objects.get(email="new.student@test.local")
        self.assertEqual(user.role, Role.STUDENT)
        self.assertTrue(user.check_password("Str0ng!Portal2026"))
        self.assertNotEqual(user.password, "Str0ng!Portal2026")  # hashed

    def test_registration_is_audited(self):
        self.client.post(self.url, self._payload())
        self.assertTrue(
            AuditLog.objects.filter(action=AuditAction.REGISTER).exists()
        )

    def test_duplicate_email_is_rejected(self):
        make_student(email="new.student@test.local", department=self.department)
        response = self.client.post(self.url, self._payload())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists")

    def test_duplicate_identifier_is_rejected(self):
        make_student(
            email="someone@test.local",
            department=self.department,
            identifier="BSIT-22-999999",
        )
        response = self.client.post(self.url, self._payload())
        self.assertContains(response, "already registered")

    def test_password_mismatch_is_rejected(self):
        response = self.client.post(
            self.url, self._payload(password2="Different!2026")
        )
        self.assertContains(response, "did not match")
        self.assertFalse(User.objects.filter(email="new.student@test.local").exists())

    def test_weak_password_is_rejected(self):
        form = StudentSignUpForm(
            data=self._payload(password1="12345678", password2="12345678")
        )
        self.assertFalse(form.is_valid())
        self.assertIn("password1", form.errors)

    def test_missing_required_fields_are_reported(self):
        form = StudentSignUpForm(data={})
        self.assertFalse(form.is_valid())
        for field in ("full_name", "email", "identifier", "department", "password1"):
            self.assertIn(field, form.errors)

    def test_terms_must_be_accepted(self):
        payload = self._payload()
        payload.pop("accept_terms")
        form = StudentSignUpForm(data=payload)
        self.assertFalse(form.is_valid())
        self.assertIn("accept_terms", form.errors)

    def test_public_signup_cannot_escalate_to_admin(self):
        """Even if the client posts a role, only STUDENT is ever created."""
        self.client.post(self.url, self._payload(role=Role.ADMIN))
        user = User.objects.get(email="new.student@test.local")
        self.assertEqual(user.role, Role.STUDENT)

    def test_authenticated_user_is_redirected_away(self):
        self.client.force_login(make_student(department=self.department))
        response = self.client.get(self.url)
        self.assertRedirects(response, reverse("dashboards:home"), target_status_code=302)


class LoginTests(TestCase):
    def setUp(self):
        self.department = make_department()
        self.student = make_student(
            email="login.student@test.local",
            department=self.department,
            identifier="BSIT-000111",
        )
        self.url = reverse("accounts:login")

    def test_login_page_renders(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "LOGIN")

    def test_login_with_email_succeeds(self):
        response = self.client.post(
            self.url, {"username": self.student.email, "password": PASSWORD}
        )
        self.assertRedirects(
            response, reverse("dashboards:home"), target_status_code=302
        )
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.student.pk)

    def test_login_with_identifier_succeeds(self):
        response = self.client.post(
            self.url, {"username": "BSIT-000111", "password": PASSWORD}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.student.pk)

    def test_wrong_password_shows_error_message(self):
        response = self.client.post(
            self.url, {"username": self.student.email, "password": "wrong-password"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid credentials")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_unknown_user_shows_error_message(self):
        response = self.client.post(
            self.url, {"username": "ghost@test.local", "password": PASSWORD}
        )
        self.assertContains(response, "Invalid credentials")

    def test_deactivated_account_cannot_sign_in(self):
        self.student.is_active = False
        self.student.save(update_fields=["is_active"])
        response = self.client.post(
            self.url, {"username": self.student.email, "password": PASSWORD}
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_successful_login_is_audited(self):
        self.client.post(self.url, {"username": self.student.email, "password": PASSWORD})
        self.assertTrue(AuditLog.objects.filter(action=AuditAction.LOGIN_SUCCESS).exists())

    def test_failed_login_is_audited(self):
        self.client.post(self.url, {"username": self.student.email, "password": "nope"})
        entry = AuditLog.objects.filter(action=AuditAction.LOGIN_FAILED).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.target, self.student.email)

    def test_logout_clears_session_and_is_audited(self):
        self.client.force_login(self.student)
        response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(response, reverse("accounts:login"))
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertTrue(AuditLog.objects.filter(action=AuditAction.LOGOUT).exists())


@override_settings(AXES_ENABLED=True, AXES_FAILURE_LIMIT=3)
class BruteForceLockoutTests(TestCase):
    """django-axes lockout, exercised through the real login view (NFR security)."""

    def setUp(self):
        from axes.models import AccessAttempt

        AccessAttempt.objects.all().delete()
        self.department = make_department()
        self.student = make_student(
            email="lockme@test.local", department=self.department
        )
        self.url = reverse("accounts:login")

    def tearDown(self):
        from axes.handlers.proxy import AxesProxyHandler

        AxesProxyHandler.reset_attempts()

    def test_repeated_failures_lock_the_account(self):
        for _ in range(3):
            self.client.post(
                self.url, {"username": self.student.email, "password": "wrong"}
            )
        # The correct password no longer authenticates while locked out.
        self.client.post(
            self.url, {"username": self.student.email, "password": PASSWORD}
        )
        self.assertNotIn("_auth_user_id", self.client.session)


class ProfileTests(TestCase):
    def setUp(self):
        self.department = make_department()
        self.student = make_student(department=self.department)
        self.url = reverse("accounts:profile")

    def test_profile_requires_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    def test_profile_can_be_updated(self):
        self.client.force_login(self.student)
        response = self.client.post(
            self.url, {"full_name": "Updated Name", "phone": "0311-0000000"}
        )
        self.assertRedirects(response, self.url)
        self.student.refresh_from_db()
        self.assertEqual(self.student.full_name, "Updated Name")

    def test_invalid_profile_update_is_rejected(self):
        self.client.force_login(self.student)
        response = self.client.post(self.url, {"full_name": "", "phone": ""})
        self.assertEqual(response.status_code, 200)
        self.student.refresh_from_db()
        self.assertNotEqual(self.student.full_name, "")


class AdminUserFormTests(TestCase):
    """FR-10 business rules: invalid role assignments must be blocked."""

    def setUp(self):
        self.department = make_department()

    def _payload(self, **overrides):
        payload = {
            "full_name": "Staff Member",
            "email": "staff@test.local",
            "identifier": "STAFF-001",
            "phone": "",
            "role": Role.HOD,
            "department": self.department.pk,
            "is_active": "on",
            "password1": "Str0ng!Portal2026",
            "password2": "Str0ng!Portal2026",
        }
        payload.update(overrides)
        return payload

    def test_hod_requires_a_department(self):
        form = AdminUserForm(data=self._payload(department=""))
        self.assertFalse(form.is_valid())
        self.assertIn("department", form.errors)

    def test_admin_department_is_discarded(self):
        form = AdminUserForm(data=self._payload(role=Role.ADMIN))
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertIsNone(user.department_id)

    def test_password_is_hashed_on_create(self):
        form = AdminUserForm(data=self._payload())
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertTrue(user.check_password("Str0ng!Portal2026"))

    def test_blank_password_on_edit_keeps_existing_one(self):
        existing = make_hod(email="existing@test.local", department=self.department)
        form = AdminUserForm(
            data=self._payload(
                email="existing@test.local", password1="", password2=""
            ),
            instance=existing,
        )
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertTrue(user.check_password(PASSWORD))

    def test_duplicate_email_is_rejected(self):
        make_admin(email="staff@test.local")
        form = AdminUserForm(data=self._payload())
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_duplicate_identifier_is_rejected(self):
        make_admin(email="other.admin@test.local", identifier="STAFF-001")
        form = AdminUserForm(data=self._payload())
        self.assertFalse(form.is_valid())
        self.assertIn("identifier", form.errors)
