"""
Production settings.

Everything sensitive is read from the environment. Running
``python manage.py check --deploy --settings=config.settings.prod``
must report zero issues.
"""

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import SECRET_KEY, env

DEBUG = False

ALLOWED_HOSTS = env("ALLOWED_HOSTS")

# Refuse to start rather than silently running production on the development
# fallback key. Generate one with:
#   python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
if SECRET_KEY.startswith("django-insecure-") or len(SECRET_KEY) < 50:
    raise ImproperlyConfigured(
        "SECRET_KEY must be set to a unique, random value of at least 50 "
        "characters before running with config.settings.prod. See .env.example."
    )

# --------------------------------------------------------------------------
# HTTPS / transport security
# --------------------------------------------------------------------------
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31536000)  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# --------------------------------------------------------------------------
# Cookies
# --------------------------------------------------------------------------
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"

CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = False  # the JS fetch helper reads the token from the cookie
CSRF_COOKIE_SAMESITE = "Lax"

# --------------------------------------------------------------------------
# Content / browser protections
# --------------------------------------------------------------------------
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# --------------------------------------------------------------------------
# Static files are served by WhiteNoise (free, no CDN account required)
# --------------------------------------------------------------------------
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
WHITENOISE_MAX_AGE = 60 * 60 * 24 * 30

# Notifications are dispatched off the request thread in production.
NOTIFICATIONS_ASYNC = env.bool("NOTIFICATIONS_ASYNC", default=True)
