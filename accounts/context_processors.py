"""Expose branding + role flags to every template."""

from django.conf import settings


def portal_context(request):
    user = getattr(request, "user", None)
    authenticated = bool(user and user.is_authenticated)
    return {
        "INSTITUTION_NAME": settings.INSTITUTION_NAME,
        "PORTAL_NAME": settings.PORTAL_NAME,
        "PORTAL_SHORT_NAME": settings.PORTAL_SHORT_NAME,
        "is_student": authenticated and user.is_student,
        "is_hod": authenticated and user.is_hod,
        "is_admin_role": authenticated and user.is_admin_role,
    }
