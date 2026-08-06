"""Development settings: verbose, permissive, zero external dependencies."""

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = True

ALLOWED_HOSTS = ["*"]

# Emails are printed to the console in development - no SMTP account needed.
EMAIL_BACKEND = env(
    "EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend"
)

# Send mail inline so the developer sees it immediately in the runserver output.
NOTIFICATIONS_ASYNC = False

# ManifestStaticFilesStorage requires `collectstatic`; plain storage is friendlier
# during development.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# Relaxed HTTPS expectations - the dev server speaks plain HTTP.
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# Serve static files straight from STATICFILES_DIRS - no collectstatic needed.
WHITENOISE_AUTOREFRESH = True
