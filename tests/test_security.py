"""
Security and hardening regression tests.

These assert the guarantees the SRS makes in sections 2.4.4 and 3.1: CSRF on
every form, no plaintext passwords, no raw SQL, safe uploads, and a production
settings module that passes ``check --deploy``.
"""

import re
from pathlib import Path

from django.conf import settings
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from complaints.models import ComplaintCategory

from .factories import PASSWORD, make_admin, make_complaint, make_department, make_student

PROJECT_ROOT = Path(settings.BASE_DIR)
APP_DIRS = ["accounts", "complaints", "dashboards", "notifications", "config"]


class CsrfProtectionTests(TestCase):
    """Every state-changing endpoint must reject a request without a token."""

    def setUp(self):
        self.department = make_department()
        self.student = make_student(department=self.department)
        self.complaint = make_complaint(
            student=self.student, department=self.department
        )
        # enforce_csrf_checks mirrors a real browser request.
        self.client = Client(enforce_csrf_checks=True)

    def test_login_without_a_csrf_token_is_rejected(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": self.student.email, "password": PASSWORD},
        )
        self.assertEqual(response.status_code, 403)

    def test_registration_without_a_csrf_token_is_rejected(self):
        response = self.client.post(reverse("accounts:signup"), {})
        self.assertEqual(response.status_code, 403)

    def test_complaint_submission_without_a_csrf_token_is_rejected(self):
        self.client.force_login(self.student)
        response = self.client.post(
            reverse("complaints:create"),
            {
                "subject": "A complaint without a token",
                "category": ComplaintCategory.OTHER,
                "department": self.department.pk,
                "description": "This request carries no CSRF token whatsoever.",
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_cancel_without_a_csrf_token_is_rejected(self):
        self.client.force_login(self.student)
        response = self.client.post(
            reverse("complaints:cancel", args=[self.complaint.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_forms_render_a_csrf_token(self):
        client = Client()
        for url in (reverse("accounts:login"), reverse("accounts:signup")):
            with self.subTest(url=url):
                self.assertContains(client.get(url), "csrfmiddlewaretoken")


class PasswordStorageTests(TestCase):
    def test_passwords_are_hashed_never_stored_in_plaintext(self):
        department = make_department()
        user = make_student(department=department)
        self.assertNotEqual(user.password, PASSWORD)
        self.assertNotIn(PASSWORD, user.password)
        self.assertTrue(user.check_password(PASSWORD))

    def test_password_is_never_rendered_in_a_response(self):
        department = make_department()
        student = make_student(department=department)
        admin = make_admin()
        self.client.force_login(admin)
        response = self.client.get(
            reverse("dashboards:user_edit", args=[student.pk])
        )
        self.assertNotContains(response, student.password)


class HttpMethodTests(TestCase):
    """Destructive actions must not be reachable by a GET."""

    def setUp(self):
        self.department = make_department()
        self.student = make_student(department=self.department)
        self.admin = make_admin()
        self.complaint = make_complaint(
            student=self.student, department=self.department
        )

    def test_cancel_rejects_get(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("complaints:cancel", args=[self.complaint.pk]))
        self.assertEqual(response.status_code, 405)

    def test_status_update_rejects_get(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("complaints:status", args=[self.complaint.pk]))
        self.assertEqual(response.status_code, 405)

    def test_user_toggle_rejects_get(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("dashboards:user_toggle", args=[self.student.pk])
        )
        self.assertEqual(response.status_code, 405)


class MediaExposureTests(TestCase):
    def test_media_is_not_served_by_a_public_url_pattern(self):
        """Uploads are reachable only through complaints:attachment."""
        from config import urls

        patterns = [str(getattr(p, "pattern", "")) for p in urls.urlpatterns]
        media_prefix = settings.MEDIA_URL.strip("/")
        self.assertFalse(
            any(pattern.strip("^/").startswith(media_prefix) for pattern in patterns),
            "MEDIA_URL must not be routed directly - it bypasses access control.",
        )


class NoRawSqlTests(TestCase):
    """The SRS mandates ORM-only data access (SQL-injection mitigation)."""

    FORBIDDEN = re.compile(
        r"\.raw\(|RawSQL|cursor\(\)\.execute|connection\.cursor\("
    )

    def test_application_code_contains_no_raw_sql(self):
        offenders = []
        for app in APP_DIRS:
            for path in (PROJECT_ROOT / app).rglob("*.py"):
                if "migrations" in path.parts:
                    continue
                text = path.read_text(encoding="utf-8")
                if self.FORBIDDEN.search(text):
                    offenders.append(str(path.relative_to(PROJECT_ROOT)))
        self.assertEqual(offenders, [], f"Raw SQL found in: {offenders}")


class SecretsHygieneTests(TestCase):
    def test_no_hardcoded_secret_key_outside_the_settings_fallback(self):
        """Only base.py may name a fallback key, and only as an env default."""
        offenders = []
        for app in APP_DIRS:
            for path in (PROJECT_ROOT / app).rglob("*.py"):
                if path.name == "base.py":
                    continue
                text = path.read_text(encoding="utf-8")
                if re.search(r"^SECRET_KEY\s*=\s*[\"']", text, re.MULTILINE):
                    offenders.append(str(path.relative_to(PROJECT_ROOT)))
        self.assertEqual(offenders, [])

    def test_env_file_is_git_ignored(self):
        gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
        for entry in (".env", "db.sqlite3", ".venv/"):
            self.assertIn(entry, gitignore)

    def test_env_example_ships_no_real_credentials(self):
        example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertIn("SECRET_KEY=replace-me", example)
        self.assertRegex(example, r"(?m)^EMAIL_HOST_PASSWORD=\s*$")
        self.assertRegex(example, r"(?m)^DB_PASSWORD=\s*$")


class ZeroCostDependencyTests(TestCase):
    """
    Guards the project's zero-cost constraint: no dependency may be a client for
    a paid or billed service.
    """

    PAID_SERVICE_PACKAGES = {
        "sendgrid",
        "mailgun",
        "boto3",
        "botocore",
        "twilio",
        "stripe",
        "sentry-sdk",
        "google-cloud-storage",
        "azure-storage-blob",
        "newrelic",
        "datadog",
        "algoliasearch",
        "openai",
        "anthropic",
    }

    def _requirement_names(self):
        text = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
        names = []
        for line in text.splitlines():
            line = line.split("#")[0].strip()
            if line:
                names.append(re.split(r"[=<>!~\[]", line)[0].strip().lower())
        return names

    def test_requirements_are_pinned(self):
        text = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.split("#")[0].strip()
            if line:
                self.assertIn("==", line, f"Unpinned requirement: {line}")

    def test_no_paid_service_client_is_required(self):
        overlap = self.PAID_SERVICE_PACKAGES.intersection(self._requirement_names())
        self.assertEqual(overlap, set(), f"Paid-service dependency found: {overlap}")

    def test_email_configuration_uses_free_smtp_only(self):
        example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8").lower()
        for paid in ("sendgrid", "mailgun", "amazonses", "postmark"):
            self.assertNotIn(paid, example)
        self.assertIn("smtp.gmail.com", example)

    def test_frontend_assets_are_vendored_not_cdn_hosted(self):
        """No external CDN: the college server may sit behind a strict firewall."""
        for name in ("bootstrap.min.css",):
            self.assertTrue((PROJECT_ROOT / "static" / "css" / name).exists())
        for name in ("bootstrap.bundle.min.js", "chart.umd.min.js"):
            self.assertTrue((PROJECT_ROOT / "static" / "js" / name).exists())

        base_template = (PROJECT_ROOT / "templates" / "base.html").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("cdn.jsdelivr.net", base_template)
        self.assertNotIn("https://", base_template)


@override_settings(
    SECURE_HSTS_SECONDS=31536000,
    SECURE_HSTS_INCLUDE_SUBDOMAINS=True,
    SECURE_HSTS_PRELOAD=True,
    SECURE_SSL_REDIRECT=True,
    SESSION_COOKIE_SECURE=True,
    CSRF_COOKIE_SECURE=True,
    SECURE_CONTENT_TYPE_NOSNIFF=True,
    SECURE_REFERRER_POLICY="same-origin",
    X_FRAME_OPTIONS="DENY",
    DEBUG=False,
)
class DeploymentCheckTests(TestCase):
    """The production security posture must satisfy Django's own deploy checks."""

    def test_deployment_checks_report_no_issues(self):
        from django.core.checks import Tags, run_checks

        issues = [
            issue
            for issue in run_checks(tags=[Tags.security], include_deployment_checks=True)
            # W009 concerns the test SECRET_KEY, which is never used in production
            # (config.settings.prod refuses to start without a real one).
            if issue.id != "security.W009"
        ]
        self.assertEqual(issues, [], f"Deployment issues: {issues}")

    def test_production_settings_module_defines_the_expected_hardening(self):
        """
        Load config.settings.prod for real, with a valid key supplied through the
        environment exactly as a deployment would.
        """
        import importlib
        import os
        import sys
        from unittest import mock

        strong_key = "k" + "".join(chr(97 + (i % 26)) for i in range(64))
        env = {"SECRET_KEY": strong_key, "ALLOWED_HOSTS": "complaints.example.edu"}

        try:
            with mock.patch.dict(os.environ, env):
                base = importlib.reload(importlib.import_module("config.settings.base"))
                self.assertEqual(base.SECRET_KEY, strong_key)
                prod = importlib.import_module("config.settings.prod")
                prod = importlib.reload(prod)
        finally:
            # Restore the module cache so later tests see the original modules.
            sys.modules.pop("config.settings.prod", None)
            importlib.reload(importlib.import_module("config.settings.base"))

        self.assertFalse(prod.DEBUG)
        self.assertEqual(prod.ALLOWED_HOSTS, ["complaints.example.edu"])
        self.assertTrue(prod.SESSION_COOKIE_SECURE)
        self.assertTrue(prod.CSRF_COOKIE_SECURE)
        self.assertTrue(prod.SECURE_CONTENT_TYPE_NOSNIFF)
        self.assertTrue(prod.SECURE_HSTS_INCLUDE_SUBDOMAINS)
        self.assertEqual(prod.X_FRAME_OPTIONS, "DENY")
        self.assertGreaterEqual(prod.SECURE_HSTS_SECONDS, 31536000)

    def test_production_refuses_a_placeholder_secret_key(self):
        source = (
            PROJECT_ROOT / "config" / "settings" / "prod.py"
        ).read_text(encoding="utf-8")
        self.assertIn("ImproperlyConfigured", source)
        self.assertIn("django-insecure-", source)
