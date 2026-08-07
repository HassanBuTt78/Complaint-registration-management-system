"""
Deployment configuration guards.

These lock in the settings that make the app survive a serverless runtime.
Each one corresponds to a way the deployment would silently misbehave: losing
uploads, losing email, 500ing on every static asset, or exhausting the database
connection limit. They run against the *real* settings modules rather than
mocks, so drift is caught here rather than in production.
"""

import copy
import importlib
import io
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from django.conf import settings
from django.test import SimpleTestCase

PROJECT_ROOT = Path(settings.BASE_DIR)


def load_settings_module(name, env_overrides):
    """
    Import a settings module under a controlled environment.

    ``config.settings.base`` is reloaded first: the environment is read at *its*
    import time, and Python would otherwise hand back the already-cached module
    with values captured when the test runner started.
    """
    original = {}
    for key, value in env_overrides.items():
        original[key] = os.environ.get(key)
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    try:
        base = importlib.import_module("config.settings.base")
        importlib.reload(base)
        if name == "config.settings.base":
            module = base
        else:
            module = importlib.reload(importlib.import_module(name))
        # Snapshot the values. `importlib.reload` mutates the module object in
        # place, so the restore in `finally` would otherwise rewrite the very
        # attributes the caller is about to assert on.
        return SimpleNamespace(
            **{
                key: copy.deepcopy(getattr(module, key))
                for key in dir(module)
                if key.isupper()
            }
        )
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        # Restore the module cache so later tests see the real settings.
        importlib.reload(importlib.import_module("config.settings.base"))


VERCEL_ENV = {
    "DATABASE_URL": "postgresql://user:pass@db.example.neon.tech:5432/portal",
    "VERCEL_URL": "ocr-portal.vercel.app",
    "SECRET_KEY": "test-only-secret-key-for-settings-inspection-000000",
}


class VercelSettingsTests(SimpleTestCase):
    """The serverless settings module makes the right choices."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cfg = load_settings_module("config.settings.vercel", VERCEL_ENV)

    def test_debug_is_off(self):
        self.assertFalse(self.cfg.DEBUG)

    def test_uses_postgres_from_database_url(self):
        self.assertIn("postgresql", self.cfg.DATABASES["default"]["ENGINE"])
        self.assertEqual(self.cfg.DATABASES["default"]["NAME"], "portal")

    def test_requires_ssl_for_postgres(self):
        self.assertEqual(
            self.cfg.DATABASES["default"]["OPTIONS"].get("sslmode"), "require"
        )

    def test_connections_are_not_persisted_between_invocations(self):
        """Serverless concurrency would otherwise exhaust the connection limit."""
        self.assertEqual(self.cfg.DATABASES["default"]["CONN_MAX_AGE"], 0)

    def test_server_side_cursors_disabled_for_transaction_pooling(self):
        self.assertTrue(self.cfg.DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"])

    def test_attachments_are_stored_in_the_database(self):
        """The filesystem is read-only, so FR-4 depends on this being true."""
        self.assertTrue(self.cfg.USE_DATABASE_FILE_STORAGE)

    def test_email_is_sent_inline(self):
        """A worker thread may never run: the process freezes after responding."""
        self.assertFalse(self.cfg.NOTIFICATIONS_ASYNC)

    def test_static_files_resolve_without_collectstatic(self):
        self.assertTrue(self.cfg.WHITENOISE_USE_FINDERS)
        self.assertNotIn("Manifest", self.cfg.STORAGES["staticfiles"]["BACKEND"])

    def test_static_root_exists_so_whitenoise_does_not_warn(self):
        self.assertTrue(Path(self.cfg.STATIC_ROOT).is_dir())

    def test_deployment_host_is_trusted(self):
        self.assertIn("ocr-portal.vercel.app", self.cfg.ALLOWED_HOSTS)

    def test_csrf_trusts_the_deployment_origin(self):
        self.assertTrue(
            any("ocr-portal.vercel.app" in o for o in self.cfg.CSRF_TRUSTED_ORIGINS)
        )

    def test_no_file_log_handler_on_read_only_filesystem(self):
        self.assertNotIn("file", self.cfg.LOGGING["handlers"])

    def test_security_headers_are_configured(self):
        self.assertTrue(self.cfg.SECURE_SSL_REDIRECT)
        self.assertTrue(self.cfg.SESSION_COOKIE_SECURE)
        self.assertTrue(self.cfg.CSRF_COOKIE_SECURE)
        self.assertTrue(self.cfg.SECURE_CONTENT_TYPE_NOSNIFF)
        self.assertEqual(self.cfg.X_FRAME_OPTIONS, "DENY")
        self.assertGreaterEqual(self.cfg.SECURE_HSTS_SECONDS, 31536000)
        self.assertEqual(
            self.cfg.SECURE_PROXY_SSL_HEADER, ("HTTP_X_FORWARDED_PROTO", "https")
        )


class MissingDatabaseUrlTests(SimpleTestCase):
    """Refusing to boot beats silently discarding every complaint."""

    def test_boot_without_database_url_fails_with_actionable_message(self):
        probe = subprocess.run(
            [
                sys.executable,
                "-c",
                "import os, sys;"
                f"sys.path.insert(0, r'{PROJECT_ROOT}');"
                "os.environ.pop('DATABASE_URL', None);"
                "os.environ.pop('POSTGRES_URL', None);"
                "os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.vercel';"
                "import django; django.setup()",
            ],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        self.assertNotEqual(probe.returncode, 0)
        self.assertIn("DATABASE_URL is not set", probe.stderr)
        self.assertIn("DEPLOY_VERCEL.md", probe.stderr)


class DatabaseUrlPrecedenceTests(SimpleTestCase):
    """DATABASE_URL overrides the SQLite/MySQL defaults in base settings."""

    def test_database_url_wins_over_sqlite_default(self):
        cfg = load_settings_module(
            "config.settings.base",
            {
                "DATABASE_URL": "postgresql://u:p@example.com:5432/mydb",
                "SECRET_KEY": "test-only-secret-key-000000000000000000000000",
            },
        )
        self.assertIn("postgresql", cfg.DATABASES["default"]["ENGINE"])
        self.assertEqual(cfg.DATABASES["default"]["NAME"], "mydb")

    def test_sqlite_is_used_when_no_url_is_supplied(self):
        cfg = load_settings_module(
            "config.settings.base",
            {
                "DATABASE_URL": None,
                "POSTGRES_URL": None,
                "DB_ENGINE": None,
                "SECRET_KEY": "test-only-secret-key-000000000000000000000000",
            },
        )
        self.assertIn("sqlite3", cfg.DATABASES["default"]["ENGINE"])


class VercelEntryPointTests(SimpleTestCase):
    """
    Drive the WSGI callable exactly as Vercel's runtime does.

    This is the closest we can get to the real thing without deploying, and it
    catches the failure mode that matters most: an entry point that imports but
    cannot actually serve a request.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.probe_env = {
            **os.environ,
            "DATABASE_URL": f"sqlite:///{PROJECT_ROOT / 'db.sqlite3'}",
            "VERCEL_URL": "ocr-portal.vercel.app",
            "SECRET_KEY": "test-only-secret-key-for-wsgi-probe-0000000000",
        }
        cls.probe_env.pop("DJANGO_SETTINGS_MODULE", None)

    def _serve(self, path, scheme="https", host="ocr-portal.vercel.app"):
        """Import the entry point in a clean process and make one request."""
        script = f"""
import io, os, sys
sys.path.insert(0, r'{PROJECT_ROOT}')
os.environ.pop('DJANGO_SETTINGS_MODULE', None)
from api.index import app
environ = {{
    'REQUEST_METHOD': 'GET',
    'PATH_INFO': {path!r},
    'QUERY_STRING': '',
    'SERVER_NAME': {host!r},
    'SERVER_PORT': '443',
    'SERVER_PROTOCOL': 'HTTP/1.1',
    'HTTP_HOST': {host!r},
    'wsgi.input': io.BytesIO(b''),
    'wsgi.errors': io.BytesIO(),
    'wsgi.url_scheme': {scheme!r},
    'wsgi.multithread': False,
    'wsgi.multiprocess': False,
    'wsgi.run_once': False,
}}
if {scheme!r} == 'https':
    environ['HTTP_X_FORWARDED_PROTO'] = 'https'
captured = {{}}
def start_response(status, headers, exc_info=None):
    captured['status'] = status
body = b''.join(app(environ, start_response))
print('STATUS:' + captured['status'])
print('LEN:' + str(len(body)))
"""
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
            env=self.probe_env,
        )
        self.assertEqual(
            result.returncode, 0, f"entry point crashed:\n{result.stderr}"
        )
        status = next(
            line.split(":", 1)[1]
            for line in result.stdout.splitlines()
            if line.startswith("STATUS:")
        )
        length = int(
            next(
                line.split(":", 1)[1]
                for line in result.stdout.splitlines()
                if line.startswith("LEN:")
            )
        )
        return status, length

    def test_entry_point_serves_the_login_page(self):
        status, length = self._serve("/accounts/login/")
        self.assertTrue(status.startswith("200"), status)
        self.assertGreater(length, 500)

    def test_entry_point_serves_static_css_without_collectstatic(self):
        status, length = self._serve("/static/css/portal.css")
        self.assertTrue(status.startswith("200"), status)
        self.assertGreater(length, 100)

    def test_plain_http_is_redirected_to_https(self):
        status, _ = self._serve("/accounts/login/", scheme="http")
        self.assertTrue(status.startswith("301"), status)

    def test_unknown_host_header_is_rejected(self):
        status, _ = self._serve("/accounts/login/", host="attacker.example.com")
        self.assertTrue(status.startswith("400"), status)
