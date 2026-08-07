"""
Settings for deployment to Vercel (or any comparable serverless runtime).

A serverless function differs from a normal server in four ways that matter
here, and each one is addressed below:

1. **The filesystem is read-only** (bar an ephemeral ``/tmp``). SQLite and
   on-disk uploads would both lose data, so this module requires a managed
   Postgres database and routes attachments into it.
2. **The process is frozen the moment the response is returned.** A background
   thread may never run, so notification email is sent inline.
3. **There is no build step running ``collectstatic``.** WhiteNoise is put into
   finders mode so it serves straight from ``static/``.
4. **Connections are not reused between invocations.** Persistent database
   connections are disabled to avoid exhausting the connection limit.

Everything required is available on a free tier with no card: Vercel Hobby for
hosting and Neon or Supabase for Postgres.
"""

import tempfile
from pathlib import Path

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = False

# ---------------------------------------------------------------------------
# Hosts
#
# Vercel injects VERCEL_URL (the deployment's own hostname, without a scheme).
# Any custom domain is added through ALLOWED_HOSTS.
# ---------------------------------------------------------------------------
ALLOWED_HOSTS = [".vercel.app"]

_vercel_host = env("VERCEL_URL", default="")
if _vercel_host:
    ALLOWED_HOSTS.append(_vercel_host)

_project_host = env("VERCEL_PROJECT_PRODUCTION_URL", default="")
if _project_host:
    ALLOWED_HOSTS.append(_project_host)

ALLOWED_HOSTS += [h for h in env("ALLOWED_HOSTS", default=[]) if h]

CSRF_TRUSTED_ORIGINS = ["https://*.vercel.app"] + [
    origin if origin.startswith("http") else f"https://{origin}"
    for origin in env("CSRF_TRUSTED_ORIGINS", default=[])
    if origin
]
for _host in (_vercel_host, _project_host):
    if _host:
        CSRF_TRUSTED_ORIGINS.append(f"https://{_host}")

# ---------------------------------------------------------------------------
# Database - managed Postgres is mandatory
#
# Failing loudly here is deliberate. Falling back to SQLite on a read-only,
# per-invocation filesystem would "work" on the first request and then quietly
# discard every complaint, which is far worse than refusing to start.
# ---------------------------------------------------------------------------
# base.py already turns DATABASE_URL into DATABASES["default"]; this only
# enforces that it was actually provided.
if not DATABASE_URL:  # noqa: F405
    raise RuntimeError(
        "DATABASE_URL is not set.\n\n"
        "Vercel's filesystem is read-only, so SQLite cannot be used - complaint "
        "data would be lost on every request. Create a free Postgres database "
        "(Neon or Supabase, no card required) and add its connection string as "
        "the DATABASE_URL environment variable in your Vercel project settings.\n"
        "See DEPLOY_VERCEL.md for step-by-step instructions."
    )

# Serverless invocations are short-lived and highly concurrent. Reusing
# connections would exhaust the database's connection limit, and server-side
# cursors break behind a transaction pooler such as Neon's pgbouncer endpoint.
DATABASES["default"]["CONN_MAX_AGE"] = 0
DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True
DATABASES["default"].setdefault("OPTIONS", {})
DATABASES["default"]["OPTIONS"].setdefault("connect_timeout", 10)
if DATABASES["default"].get("ENGINE", "").endswith("postgresql"):
    DATABASES["default"]["OPTIONS"].setdefault("sslmode", "require")

# ---------------------------------------------------------------------------
# Attachments live in the database (FR-4)
#
# There is nowhere on disk to persist an upload, and object storage would mean
# a paid or account-gated service. See complaints/storage.py.
# ---------------------------------------------------------------------------
USE_DATABASE_FILE_STORAGE = True

# ---------------------------------------------------------------------------
# Email must be sent inline
#
# The runtime suspends the process as soon as the response is flushed, so a
# daemon thread is not guaranteed to finish. Failures are still caught and
# recorded rather than raised (FR-9).
# ---------------------------------------------------------------------------
NOTIFICATIONS_ASYNC = False
EMAIL_TIMEOUT = 10

# ---------------------------------------------------------------------------
# Static files
#
# Nothing runs `collectstatic` during a Vercel Python build, so WhiteNoise is
# told to resolve files through the staticfiles finders. The manifest storage
# backend is deliberately not used: it requires a manifest that only
# `collectstatic` produces, and would raise on every request without one.
# ---------------------------------------------------------------------------
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = False
WHITENOISE_MAX_AGE = 60 * 60 * 24 * 7

# WhiteNoise emits "No directory at: .../staticfiles/" on every cold start when
# STATIC_ROOT is absent, which it always is here because nothing runs
# collectstatic. Point it at a real (empty) directory under the writable
# temp mount: files are resolved through the finders above, and the log stays
# clean.
_static_root = Path(tempfile.gettempdir()) / "ocr-portal-staticfiles"
try:
    _static_root.mkdir(parents=True, exist_ok=True)
    STATIC_ROOT = _static_root
except OSError:  # pragma: no cover - temp dir is writable on every host
    pass

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

# ---------------------------------------------------------------------------
# Transport & cookie security
#
# Vercel terminates TLS at the edge and forwards X-Forwarded-Proto, so Django
# must trust that header to know the original request was HTTPS.
# ---------------------------------------------------------------------------
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)

SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"

CSRF_COOKIE_SECURE = True
CSRF_COOKIE_SAMESITE = "Lax"

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# ---------------------------------------------------------------------------
# Logging
#
# The log directory created in base.py is not writable at runtime, so logs go to
# stdout only - which is exactly what Vercel's log drain collects.
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "{levelname} {name} {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
        "notifications": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "accounts.security": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
