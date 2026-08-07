"""
Base settings shared by every environment.

All secrets and environment-specific values are read from the environment
(optionally populated from a ``.env`` file). See ``.env.example``.
"""

import os
from pathlib import Path

import environ

# complaint_system/config/settings/base.py -> BASE_DIR = complaint_system/
BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CSRF_TRUSTED_ORIGINS=(list, []),
    DB_ENGINE=(str, "sqlite"),
    DB_NAME=(str, "complaint_system"),
    DB_USER=(str, ""),
    DB_PASSWORD=(str, ""),
    DB_HOST=(str, "127.0.0.1"),
    DB_PORT=(str, "3306"),
    EMAIL_BACKEND=(str, "django.core.mail.backends.console.EmailBackend"),
    EMAIL_HOST=(str, "smtp.gmail.com"),
    EMAIL_PORT=(int, 587),
    EMAIL_USE_TLS=(bool, True),
    EMAIL_HOST_USER=(str, ""),
    EMAIL_HOST_PASSWORD=(str, ""),
    DEFAULT_FROM_EMAIL=(str, "Complaint Portal <no-reply@mao-college.local>"),
    NOTIFICATIONS_ASYNC=(bool, True),
    AXES_FAILURE_LIMIT=(int, 5),
    AXES_COOLOFF_MINUTES=(int, 15),
    MAX_UPLOAD_SIZE_MB=(int, 5),
    SECRET_KEY=(str, "django-insecure-change-me-in-production-0000000000000000"),
)

# Load .env if present (never required - sane defaults keep dev frictionless).
_env_file = BASE_DIR / ".env"
if _env_file.exists():
    environ.Env.read_env(str(_env_file))

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    # Third party (all free / open source)
    "axes",
    # Local
    "accounts",
    "complaints",
    "dashboards",
    "notifications",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "axes.middleware.AxesMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "accounts.context_processors.portal_context",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# --------------------------------------------------------------------------
# Database
#
# Precedence:
#   1. DATABASE_URL  - a single connection string (Postgres on Neon/Supabase,
#      and what hosted platforms inject). Setting it locally also lets you run
#      `migrate` and `seed_demo_data` against the deployed database.
#   2. DB_ENGINE=mysql - discrete MySQL 8 settings.
#   3. SQLite - the zero-configuration default.
# --------------------------------------------------------------------------
DATABASE_URL = env("DATABASE_URL", default="") or env("POSTGRES_URL", default="")

if DATABASE_URL:
    DATABASES = {"default": env.db_url_config(DATABASE_URL)}
    DATABASES["default"].setdefault("OPTIONS", {})
    if DATABASES["default"].get("ENGINE", "").endswith("postgresql"):
        DATABASES["default"]["OPTIONS"].setdefault("sslmode", "require")
elif env("DB_ENGINE") == "mysql":
    # PyMySQL is a pure-python driver: no compiler, no paid license, installs
    # everywhere. It registers itself as MySQLdb for Django's mysql backend.
    import pymysql

    pymysql.install_as_MySQLdb()

    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": env("DB_NAME"),
            "USER": env("DB_USER"),
            "PASSWORD": env("DB_PASSWORD"),
            "HOST": env("DB_HOST"),
            "PORT": env("DB_PORT"),
            "OPTIONS": {
                "charset": "utf8mb4",
                "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
            },
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --------------------------------------------------------------------------
# Authentication
# --------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    # AxesStandaloneBackend must come first so lockouts are honoured.
    "axes.backends.AxesStandaloneBackend",
    "accounts.backends.EmailOrIdentifierBackend",
    "django.contrib.auth.backends.ModelBackend",
]

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "dashboards:home"
LOGOUT_REDIRECT_URL = "accounts:login"

SESSION_COOKIE_AGE = 60 * 60 * 8  # 8 hours
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

# --------------------------------------------------------------------------
# django-axes - free, open-source brute force protection (FR-2 / NFR security)
# --------------------------------------------------------------------------
AXES_FAILURE_LIMIT = env("AXES_FAILURE_LIMIT")
AXES_COOLOFF_TIME = env("AXES_COOLOFF_MINUTES") / 60  # hours
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_TEMPLATE = "errors/lockout.html"
AXES_LOCKOUT_PARAMETERS = ["ip_address", "username"]
AXES_ENABLED = True

# --------------------------------------------------------------------------
# Internationalisation
# --------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Karachi"
USE_I18N = True
USE_TZ = True

# --------------------------------------------------------------------------
# Static & media
# --------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# --------------------------------------------------------------------------
# Email (free Gmail SMTP App Password in production, console in development)
# --------------------------------------------------------------------------
EMAIL_BACKEND = env("EMAIL_BACKEND")
EMAIL_HOST = env("EMAIL_HOST")
EMAIL_PORT = env("EMAIL_PORT")
EMAIL_USE_TLS = env("EMAIL_USE_TLS")
EMAIL_HOST_USER = env("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL")
EMAIL_TIMEOUT = 20

# Send notification mail on a worker thread so a slow/broken SMTP server can
# never delay or break a user request (FR-9).
NOTIFICATIONS_ASYNC = env("NOTIFICATIONS_ASYNC")

# --------------------------------------------------------------------------
# Uploads (FR-4)
# --------------------------------------------------------------------------
MAX_UPLOAD_SIZE_MB = env("MAX_UPLOAD_SIZE_MB")
MAX_UPLOAD_SIZE = MAX_UPLOAD_SIZE_MB * 1024 * 1024

# Store attachment bytes in the database instead of on disk. Required on hosts
# with a read-only or ephemeral filesystem (Vercel and similar). See
# complaints/storage.py.
USE_DATABASE_FILE_STORAGE = env.bool("USE_DATABASE_FILE_STORAGE", default=False)
ALLOWED_UPLOAD_EXTENSIONS = ["pdf", "jpg", "jpeg", "png"]
ALLOWED_UPLOAD_CONTENT_TYPES = [
    "application/pdf",
    "image/jpeg",
    "image/png",
]
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_SIZE * 2
FILE_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_SIZE

MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"

# --------------------------------------------------------------------------
# Branding
# --------------------------------------------------------------------------
INSTITUTION_NAME = "Govt. M.A.O Graduate College, Lahore"
PORTAL_NAME = "Online Complaint Registration & Management System"
PORTAL_SHORT_NAME = "OCR Portal"

# --------------------------------------------------------------------------
# Logging - errors and audit trail land on disk, never crash the request
# --------------------------------------------------------------------------
LOG_DIR = BASE_DIR / "logs"

# Serverless hosts (Vercel and similar) mount the application directory
# read-only, so creating the log directory - or writing to it - raises at import
# time. Fall back to console-only logging instead of refusing to boot; those
# platforms collect stdout anyway.
try:
    LOG_DIR.mkdir(exist_ok=True)
    _log_to_file = os.access(LOG_DIR, os.W_OK)
except OSError:
    _log_to_file = False

_log_handlers = ["console", "file"] if _log_to_file else ["console"]

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        **(
            {
                "file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "filename": str(LOG_DIR / "application.log"),
                    "maxBytes": 5 * 1024 * 1024,
                    "backupCount": 3,
                    "formatter": "verbose",
                    "encoding": "utf-8",
                }
            }
            if _log_to_file
            else {}
        ),
    },
    "root": {"handlers": _log_handlers, "level": "INFO"},
    "loggers": {
        "django.request": {
            "handlers": _log_handlers,
            "level": "ERROR",
            "propagate": False,
        },
        "notifications": {
            "handlers": _log_handlers,
            "level": "INFO",
            "propagate": False,
        },
        "accounts.security": {
            "handlers": _log_handlers,
            "level": "INFO",
            "propagate": False,
        },
    },
}
