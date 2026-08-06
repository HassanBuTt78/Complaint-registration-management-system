"""
Accounts domain: departments, the custom user with role-based access, and the
tamper-evident audit trail.

Implements FR-1 (registration), FR-2 (login), FR-10 (user management) and the
logging half of FR-12 (access control).
"""

from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Department(models.Model):
    """An academic/administrative department complaints are routed to."""

    name = models.CharField(_("department name"), max_length=120, unique=True)
    code = models.CharField(
        _("code"),
        max_length=16,
        unique=True,
        help_text=_("Short code used in reports, e.g. IT or ADM."),
    )
    description = models.CharField(_("description"), max_length=255, blank=True)
    is_active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = _("department")
        verbose_name_plural = _("departments")

    def __str__(self):
        return self.name


class Role(models.TextChoices):
    """The three tiers of the RBAC model."""

    STUDENT = "STUDENT", _("Student")
    HOD = "HOD", _("Head of Department")
    ADMIN = "ADMIN", _("Principal / Administrator")


class UserManager(BaseUserManager):
    """Manager for a user model keyed on email instead of username."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email).lower()
        extra_fields.setdefault("username", email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.full_clean(exclude=["password"])
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("role", Role.STUDENT)
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("role", Role.ADMIN)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    """
    Custom user.

    ``email`` is the login identifier; students and staff may alternatively sign
    in with their institutional ID (``identifier``) - see
    :class:`accounts.backends.EmailOrIdentifierBackend`.
    """

    # ``username`` is kept (AbstractUser requires it) but mirrors the email so
    # nothing in Django's admin/auth machinery breaks.
    email = models.EmailField(_("email address"), unique=True)
    full_name = models.CharField(_("full name"), max_length=150)
    identifier = models.CharField(
        _("student / staff ID"),
        max_length=32,
        blank=True,
        null=True,
        unique=True,
        help_text=_("Roll number for students, staff ID for HOD and Admin."),
    )
    role = models.CharField(
        _("role"), max_length=10, choices=Role.choices, default=Role.STUDENT
    )
    department = models.ForeignKey(
        Department,
        verbose_name=_("department"),
        related_name="members",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    phone = models.CharField(_("phone"), max_length=32, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    objects = UserManager()

    class Meta:
        ordering = ["full_name"]
        verbose_name = _("user")
        verbose_name_plural = _("users")
        indexes = [
            models.Index(fields=["role"]),
            models.Index(fields=["department"]),
        ]

    def __str__(self):
        return f"{self.full_name} <{self.email}>"

    # -- validation --------------------------------------------------------
    def clean(self):
        super().clean()
        self.email = (self.email or "").lower().strip()
        if not self.username:
            self.username = self.email
        if self.identifier is not None:
            self.identifier = self.identifier.strip() or None
        # Business rule: an HOD is meaningless without a department (FR-7).
        if self.role == Role.HOD and self.department_id is None:
            raise ValidationError(
                {"department": _("A Head of Department must belong to a department.")}
            )
        if self.role == Role.ADMIN:
            # The Principal has global scope; a department would be misleading.
            self.department = None

    def save(self, *args, **kwargs):
        self.email = (self.email or "").lower().strip()
        if not self.username:
            self.username = self.email
        if self.role == Role.ADMIN:
            self.department = None
        super().save(*args, **kwargs)

    # -- role helpers ------------------------------------------------------
    @property
    def is_student(self):
        return self.role == Role.STUDENT

    @property
    def is_hod(self):
        return self.role == Role.HOD

    @property
    def is_admin_role(self):
        """True for the Principal/Administrator role (not Django's is_staff)."""
        return self.role == Role.ADMIN

    @property
    def display_role(self):
        return self.get_role_display()

    def get_short_name(self):
        return self.full_name.split(" ")[0] if self.full_name else self.email

    def get_full_name(self):
        return self.full_name or self.email

    def can_view_identities(self):
        """Only the Principal/Admin may unmask anonymous complainants (FR-5)."""
        return self.is_admin_role


class AuditAction(models.TextChoices):
    LOGIN_SUCCESS = "LOGIN_SUCCESS", _("Login succeeded")
    LOGIN_FAILED = "LOGIN_FAILED", _("Login failed")
    LOGOUT = "LOGOUT", _("Logout")
    REGISTER = "REGISTER", _("Account registered")
    USER_CREATED = "USER_CREATED", _("User created")
    USER_UPDATED = "USER_UPDATED", _("User updated")
    USER_DEACTIVATED = "USER_DEACTIVATED", _("User deactivated")
    USER_ACTIVATED = "USER_ACTIVATED", _("User activated")
    COMPLAINT_CREATED = "COMPLAINT_CREATED", _("Complaint submitted")
    COMPLAINT_UPDATED = "COMPLAINT_UPDATED", _("Complaint edited")
    COMPLAINT_STATUS_CHANGED = "STATUS_CHANGED", _("Complaint status changed")
    COMPLAINT_ASSIGNED = "COMPLAINT_ASSIGNED", _("Complaint assigned")
    REMARK_ADDED = "REMARK_ADDED", _("Remark added")
    UNMASK = "UNMASK", _("Anonymous complaint unmasked")
    ACCESS_DENIED = "ACCESS_DENIED", _("Unauthorised access attempt")
    REPORT_EXPORTED = "REPORT_EXPORTED", _("Report exported")
    NOTIFICATION_FAILED = "NOTIFICATION_FAILED", _("Notification delivery failed")


class AuditLog(models.Model):
    """
    Append-only activity trail (FR-12, UC20).

    Rows are never edited or deleted by application code.
    """

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="audit_entries",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    actor_label = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("Snapshot of the actor, kept even if the account is removed."),
    )
    action = models.CharField(max_length=32, choices=AuditAction.choices)
    target = models.CharField(max_length=255, blank=True)
    detail = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-timestamp", "-id"]
        verbose_name = _("audit log entry")
        verbose_name_plural = _("audit log")
        indexes = [
            models.Index(fields=["action"]),
            models.Index(fields=["-timestamp"]),
        ]

    def __str__(self):
        target = f" -> {self.target}" if self.target else ""
        return (
            f"[{self.timestamp:%Y-%m-%d %H:%M}] {self.actor_label} "
            f"{self.action}{target}"
        )

    @classmethod
    def record(cls, *, actor=None, action, target="", detail="", request=None):
        """Create an entry defensively - auditing must never break a request."""
        ip = None
        if request is not None:
            ip = get_client_ip(request)
            if actor is None and getattr(request, "user", None) is not None:
                if request.user.is_authenticated:
                    actor = request.user
        label = ""
        if actor is not None and getattr(actor, "pk", None):
            label = f"{actor.get_full_name()} ({actor.get_role_display()})"
        elif actor is not None:
            label = str(actor)
        try:
            return cls.objects.create(
                actor=actor if getattr(actor, "pk", None) else None,
                actor_label=label or "anonymous",
                action=action,
                target=str(target)[:255],
                detail=str(detail),
                ip_address=ip,
            )
        except Exception:  # pragma: no cover - never surface audit failures
            import logging

            logging.getLogger("accounts.security").exception(
                "Failed to write audit log entry for action=%s", action
            )
            return None


def get_client_ip(request):
    """Best-effort client IP extraction (proxy aware)."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR") or None
