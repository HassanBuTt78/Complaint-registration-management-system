"""
Role-Based Access Control primitives (FR-12).

Every unauthorised attempt raises ``PermissionDenied`` (HTTP 403) *and* writes
an :class:`accounts.models.AuditLog` entry. Views must additionally scope their
querysets - see :meth:`complaints.models.ComplaintQuerySet.visible_to`.
"""

from functools import wraps

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied

from .models import AuditAction, AuditLog, Role


def deny(request, reason):
    """Log the attempt and raise 403."""
    AuditLog.record(
        action=AuditAction.ACCESS_DENIED,
        target=request.get_full_path(),
        detail=reason,
        request=request,
    )
    raise PermissionDenied(reason)


class RoleRequiredMixin(LoginRequiredMixin):
    """Restrict a class-based view to one or more roles."""

    allowed_roles: tuple = ()

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if self.allowed_roles and request.user.role not in self.allowed_roles:
            deny(
                request,
                f"Role '{request.user.role}' may not access this view "
                f"(requires one of {', '.join(self.allowed_roles)}).",
            )
        return super().dispatch(request, *args, **kwargs)


class StudentRequiredMixin(RoleRequiredMixin):
    allowed_roles = (Role.STUDENT,)


class HODRequiredMixin(RoleRequiredMixin):
    allowed_roles = (Role.HOD,)


class AdminRequiredMixin(RoleRequiredMixin):
    allowed_roles = (Role.ADMIN,)


class StaffRequiredMixin(RoleRequiredMixin):
    """HOD or Admin - the two roles that manage complaints."""

    allowed_roles = (Role.HOD, Role.ADMIN)


def role_required(*roles):
    """Function-view equivalent of :class:`RoleRequiredMixin`."""

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                from django.contrib.auth.views import redirect_to_login
                from django.conf import settings
                from django.urls import reverse

                return redirect_to_login(
                    request.get_full_path(), reverse(settings.LOGIN_URL)
                )
            if roles and request.user.role not in roles:
                deny(
                    request,
                    f"Role '{request.user.role}' may not access this view "
                    f"(requires one of {', '.join(roles)}).",
                )
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator
