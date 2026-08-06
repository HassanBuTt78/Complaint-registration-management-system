"""
Test settings.

Kept deliberately close to production: only the things that make a test suite
slow, flaky or impossible to drive are relaxed.
"""

from .base import *  # noqa: F401,F403

DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]

# django-axes intercepts `Client.login()` because it has no HttpRequest to
# inspect. Lockout behaviour is exercised explicitly through the login *view*
# in accounts/tests/test_auth.py, where a real request exists.
AXES_ENABLED = False

# Fast, deterministic hashing.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Capture mail in django.core.mail.outbox and send it inline so assertions are
# not racing a worker thread.
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
NOTIFICATIONS_ASYNC = False

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
        "TEST": {"NAME": ":memory:"},
    }
}

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

MEDIA_ROOT = BASE_DIR / "media" / "test"  # noqa: F405

LOGGING["root"]["level"] = "CRITICAL"  # noqa: F405

# WhiteNoise otherwise warns about a missing STATIC_ROOT during tests.
WHITENOISE_AUTOREFRESH = True
