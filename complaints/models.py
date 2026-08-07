"""
Complaint domain models.

Covers FR-3 (submission), FR-4 (attachments), FR-5 (anonymity), FR-6 (status
tracking), FR-7 (department scoping) and FR-8 (status updates), plus the
validated state machine described in Chapter 3 of the FYP report.
"""

import os
import re
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.text import get_valid_filename
from django.utils.translation import gettext_lazy as _

from accounts.models import Department, Role

# Imported for its side effect of registering the StoredFile model with the
# app registry, as well as for the storage selector itself.
from .storage import AttachmentStorage, StoredFile  # noqa: F401

ANONYMOUS_LABEL = _("Anonymous Complainant")


class ComplaintCategory(models.TextChoices):
    ACADEMIC = "ACADEMIC", _("Academic")
    HOSTEL = "HOSTEL", _("Hostel")
    ADMINISTRATION = "ADMINISTRATION", _("Administration")
    OTHER = "OTHER", _("Other")


class ComplaintStatus(models.TextChoices):
    SUBMITTED = "SUBMITTED", _("Submitted")
    ASSIGNED = "ASSIGNED", _("Assigned")
    IN_PROGRESS = "IN_PROGRESS", _("In Progress")
    RESOLVED = "RESOLVED", _("Resolved")
    CLOSED = "CLOSED", _("Closed")
    CANCELLED = "CANCELLED", _("Cancelled")


#: The only legal state transitions. Anything else is rejected with a
#: ``ValidationError`` at the model layer (Algorithm 10).
ALLOWED_TRANSITIONS = {
    ComplaintStatus.SUBMITTED: {ComplaintStatus.ASSIGNED, ComplaintStatus.CANCELLED},
    ComplaintStatus.ASSIGNED: {ComplaintStatus.IN_PROGRESS},
    ComplaintStatus.IN_PROGRESS: {ComplaintStatus.RESOLVED},
    ComplaintStatus.RESOLVED: {ComplaintStatus.CLOSED},
    ComplaintStatus.CLOSED: set(),
    ComplaintStatus.CANCELLED: set(),
}

#: Statuses in which the student may still edit or cancel their complaint (FR/UC5).
EDITABLE_STATUSES = {ComplaintStatus.SUBMITTED}

#: Statuses that count as "finished" for reporting purposes.
TERMINAL_STATUSES = {ComplaintStatus.CLOSED, ComplaintStatus.CANCELLED}

STATUS_BADGE_CLASS = {
    ComplaintStatus.SUBMITTED: "bg-secondary",
    ComplaintStatus.ASSIGNED: "bg-info text-dark",
    ComplaintStatus.IN_PROGRESS: "bg-warning text-dark",
    ComplaintStatus.RESOLVED: "bg-success",
    ComplaintStatus.CLOSED: "bg-dark",
    ComplaintStatus.CANCELLED: "bg-danger",
}


class InvalidTransition(ValidationError):
    """Raised when a status change violates the state machine."""


class ComplaintQuerySet(models.QuerySet):
    """Queryset-level RBAC. Never rely on template logic for access control."""

    def visible_to(self, user):
        """
        Scope complaints to what ``user`` is allowed to see (FR-7, FR-12).

        * Student -> only their own complaints
        * HOD     -> only complaints filed against their own department
        * Admin   -> everything
        """
        if not user or not user.is_authenticated:
            return self.none()
        if user.is_admin_role:
            return self
        if user.is_hod:
            if user.department_id is None:
                return self.none()
            return self.filter(department_id=user.department_id)
        return self.filter(student_id=user.pk)

    def with_related(self):
        return self.select_related("department", "student", "assigned_to")

    def open_only(self):
        return self.exclude(status__in=TERMINAL_STATUSES)


class ComplaintManager(models.Manager.from_queryset(ComplaintQuerySet)):
    pass


class Complaint(models.Model):
    """A complaint raised by a student against a department."""

    reference = models.CharField(
        _("reference"),
        max_length=20,
        unique=True,
        editable=False,
        help_text=_("Human friendly tracking code, e.g. CMP-2026-000123."),
    )
    subject = models.CharField(_("subject"), max_length=200)
    description = models.TextField(_("description"))
    category = models.CharField(
        _("category"),
        max_length=20,
        choices=ComplaintCategory.choices,
        default=ComplaintCategory.ACADEMIC,
    )
    department = models.ForeignKey(
        Department,
        verbose_name=_("department"),
        related_name="complaints",
        on_delete=models.PROTECT,
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("complainant"),
        related_name="complaints",
        on_delete=models.PROTECT,
    )
    is_anonymous = models.BooleanField(
        _("submitted anonymously"),
        default=False,
        help_text=_("Hides the complainant's identity from departmental staff."),
    )
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=ComplaintStatus.choices,
        default=ComplaintStatus.SUBMITTED,
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("assigned to"),
        related_name="assigned_complaints",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(_("submitted at"), default=timezone.now)
    updated_at = models.DateTimeField(_("last updated"), auto_now=True)
    resolved_at = models.DateTimeField(_("resolved at"), null=True, blank=True)
    closed_at = models.DateTimeField(_("closed at"), null=True, blank=True)

    objects = ComplaintManager()

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = _("complaint")
        verbose_name_plural = _("complaints")
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["department"]),
            models.Index(fields=["-created_at"]),
            models.Index(fields=["category"]),
            models.Index(fields=["status", "department"]),
        ]

    def __str__(self):
        return f"{self.reference} - {self.subject}"

    # -- persistence -------------------------------------------------------
    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = self._generate_reference()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_reference():
        year = timezone.now().year
        prefix = f"CMP-{year}-"
        last = (
            Complaint.objects.filter(reference__startswith=prefix)
            .order_by("-reference")
            .values_list("reference", flat=True)
            .first()
        )
        seq = int(last.rsplit("-", 1)[1]) + 1 if last else 1
        # Collision-safe under concurrency thanks to the unique constraint plus
        # this bounded retry.
        candidate = f"{prefix}{seq:06d}"
        while Complaint.objects.filter(reference=candidate).exists():
            seq += 1
            candidate = f"{prefix}{seq:06d}"
        return candidate

    def get_absolute_url(self):
        return reverse("complaints:detail", args=[self.pk])

    # -- state machine (Algorithm 10) --------------------------------------
    @property
    def allowed_next_statuses(self):
        return sorted(ALLOWED_TRANSITIONS.get(self.status, set()))

    def can_transition_to(self, new_status):
        return new_status in ALLOWED_TRANSITIONS.get(self.status, set())

    def transition_to(self, new_status, *, actor=None, note=""):
        """
        Move the complaint to ``new_status``.

        Raises :class:`InvalidTransition` when the move is not permitted. On
        success a :class:`ComplaintStatusHistory` row is written and the caller
        is expected to fire the notification (see
        ``complaints.services.change_status``).
        """
        if new_status not in ComplaintStatus.values:
            raise InvalidTransition(
                {"status": _("'%(s)s' is not a known status.") % {"s": new_status}}
            )
        if new_status == self.status:
            raise InvalidTransition(
                {"status": _("The complaint is already in that status.")}
            )
        if not self.can_transition_to(new_status):
            raise InvalidTransition(
                {
                    "status": _(
                        "Cannot move a complaint from '%(old)s' to '%(new)s'."
                    )
                    % {
                        "old": self.get_status_display(),
                        "new": dict(ComplaintStatus.choices).get(
                            new_status, new_status
                        ),
                    }
                }
            )

        previous = self.status
        self.status = new_status
        now = timezone.now()
        if new_status == ComplaintStatus.RESOLVED:
            self.resolved_at = now
        if new_status in TERMINAL_STATUSES:
            self.closed_at = now
        self.save(update_fields=["status", "resolved_at", "closed_at", "updated_at"])

        ComplaintStatusHistory.objects.create(
            complaint=self,
            from_status=previous,
            to_status=new_status,
            changed_by=actor if getattr(actor, "pk", None) else None,
            note=note or "",
        )
        return self

    # -- editing rules -----------------------------------------------------
    @property
    def is_editable(self):
        """UC5: a complaint may only be edited before it is assigned."""
        return self.status in EDITABLE_STATUSES

    def can_be_edited_by(self, user):
        return (
            user.is_authenticated
            and user.is_student
            and self.student_id == user.pk
            and self.is_editable
        )

    def can_be_cancelled_by(self, user):
        return self.can_be_edited_by(user) and self.can_transition_to(
            ComplaintStatus.CANCELLED
        )

    def can_be_managed_by(self, user):
        """HOD of the owning department, or the Principal."""
        if not user.is_authenticated:
            return False
        if user.is_admin_role:
            return True
        return user.is_hod and user.department_id == self.department_id

    # -- anonymity (FR-5) --------------------------------------------------
    def identity_visible_to(self, user):
        """
        Whether the complainant is shown to ``user`` during normal browsing.

        Non-anonymous complaints are visible to anyone who can already see the
        complaint. An anonymous complaint is masked for *everyone* except the
        complainant themselves - including the Principal. The Principal's
        privilege is not passive visibility but the right to run the explicit,
        audited unmask action (see :meth:`can_unmask`), which is what FR-5's
        "only Admin can unmask" business rule actually requires.
        """
        if not user or not user.is_authenticated:
            return False
        if not self.is_anonymous:
            return True
        return self.student_id == user.pk

    def can_unmask(self, user):
        """Whether ``user`` may invoke the audited unmask action (Admin only)."""
        return bool(
            user
            and user.is_authenticated
            and self.is_anonymous
            and user.can_view_identities()
        )

    def complainant_display(self, user=None):
        """Name to render for ``user`` - the single source of truth for masking."""
        if user is not None and not self.identity_visible_to(user):
            return str(ANONYMOUS_LABEL)
        if user is None and self.is_anonymous:
            return str(ANONYMOUS_LABEL)
        return self.student.get_full_name()

    def complainant_identifier(self, user=None):
        if user is not None and not self.identity_visible_to(user):
            return "-"
        if user is None and self.is_anonymous:
            return "-"
        return self.student.identifier or "-"

    def complainant_email(self, user=None):
        if user is not None and not self.identity_visible_to(user):
            return "-"
        if user is None and self.is_anonymous:
            return "-"
        return self.student.email

    # -- reporting helpers -------------------------------------------------
    @property
    def status_badge_class(self):
        return STATUS_BADGE_CLASS.get(self.status, "bg-secondary")

    @property
    def resolution_hours(self):
        """Hours between submission and resolution, or ``None`` if unresolved."""
        if not self.resolved_at:
            return None
        return round((self.resolved_at - self.created_at).total_seconds() / 3600, 2)

    @property
    def age_days(self):
        end = self.closed_at or timezone.now()
        return max((end - self.created_at).days, 0)

    def timeline(self, user):
        """Merged, chronological status changes + remarks visible to ``user``."""
        events = []
        for change in self.status_history.select_related("changed_by").all():
            events.append(
                {
                    "kind": "status",
                    "timestamp": change.changed_at,
                    "title": f"{change.get_from_status_display()} → "
                    f"{change.get_to_status_display()}",
                    "body": change.note,
                    "author": change.actor_display(self, user),
                }
            )
        for remark in self.remarks.visible_to(user, self).select_related("author"):
            events.append(
                {
                    "kind": "remark",
                    "timestamp": remark.created_at,
                    "title": "Remark added",
                    "body": remark.text,
                    "author": remark.author_display(self, user),
                }
            )
        events.append(
            {
                "kind": "created",
                "timestamp": self.created_at,
                "title": "Complaint submitted",
                "body": f"Category: {self.get_category_display()}",
                "author": self.complainant_display(user),
            }
        )
        return sorted(events, key=lambda e: e["timestamp"])


def attachment_upload_path(instance, filename):
    """
    Build a safe, non-guessable storage path.

    The original filename is sanitised and prefixed with a UUID so a hostile
    upload can neither traverse directories nor overwrite an existing file.
    """
    name = get_valid_filename(os.path.basename(filename or "upload"))
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)[-80:] or "upload"
    stem, ext = os.path.splitext(name)
    ext = ext.lower()
    complaint_id = getattr(instance.complaint, "pk", "unassigned")
    return f"attachments/{complaint_id}/{uuid.uuid4().hex}_{stem[:40]}{ext}"


class ComplaintAttachment(models.Model):
    """Supporting evidence uploaded with a complaint (FR-4)."""

    complaint = models.ForeignKey(
        Complaint, related_name="attachments", on_delete=models.CASCADE
    )
    file = models.FileField(
        _("file"),
        upload_to=attachment_upload_path,
        # Resolved at runtime: local disk in development, the database on
        # serverless hosts where the filesystem is read-only. See
        # complaints/storage.py.
        storage=AttachmentStorage(),
    )
    original_name = models.CharField(max_length=255, blank=True)
    content_type = models.CharField(max_length=100, blank=True)
    size_bytes = models.PositiveIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["uploaded_at", "id"]
        verbose_name = _("attachment")
        verbose_name_plural = _("attachments")

    def __str__(self):
        return self.original_name or os.path.basename(self.file.name)

    @property
    def size_display(self):
        kb = self.size_bytes / 1024
        if kb < 1024:
            return f"{kb:.0f} KB"
        return f"{kb / 1024:.1f} MB"

    def get_absolute_url(self):
        return reverse("complaints:attachment", args=[self.pk])


class ComplaintRemarkQuerySet(models.QuerySet):
    def visible_to(self, user, complaint=None):
        """Students never see internal staff notes."""
        if not user or not user.is_authenticated:
            return self.none()
        if user.is_student:
            return self.filter(is_internal=False)
        return self


class ComplaintRemark(models.Model):
    """A note added to a complaint by staff, or a reply by the student (UC12)."""

    complaint = models.ForeignKey(
        Complaint, related_name="remarks", on_delete=models.CASCADE
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="complaint_remarks",
        on_delete=models.SET_NULL,
        null=True,
    )
    text = models.TextField(_("remark"))
    is_internal = models.BooleanField(
        _("internal note"),
        default=False,
        help_text=_("Internal notes are hidden from the complainant."),
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = ComplaintRemarkQuerySet.as_manager()

    class Meta:
        ordering = ["created_at", "id"]
        verbose_name = _("remark")
        verbose_name_plural = _("remarks")

    def __str__(self):
        return f"Remark on {self.complaint.reference}"

    def author_display(self, complaint=None, viewer=None):
        """Mask the author when the author *is* the anonymous complainant."""
        complaint = complaint or self.complaint
        if self.author_id is None:
            return "System"
        if self.author_id == complaint.student_id:
            return complaint.complainant_display(viewer)
        return f"{self.author.get_full_name()} ({self.author.get_role_display()})"


class ComplaintStatusHistory(models.Model):
    """Immutable record of every state transition, powering the timeline (FR-6)."""

    complaint = models.ForeignKey(
        Complaint, related_name="status_history", on_delete=models.CASCADE
    )
    from_status = models.CharField(max_length=20, choices=ComplaintStatus.choices)
    to_status = models.CharField(max_length=20, choices=ComplaintStatus.choices)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="status_changes",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    note = models.TextField(blank=True)
    changed_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["changed_at", "id"]
        verbose_name = _("status change")
        verbose_name_plural = _("status changes")

    def __str__(self):
        return f"{self.complaint.reference}: {self.from_status} -> {self.to_status}"

    def actor_display(self, complaint=None, viewer=None):
        complaint = complaint or self.complaint
        if self.changed_by_id is None:
            return "System"
        if self.changed_by_id == complaint.student_id:
            return complaint.complainant_display(viewer)
        return (
            f"{self.changed_by.get_full_name()} "
            f"({self.changed_by.get_role_display()})"
        )


def staff_assignable_for(complaint):
    """Users an HOD may assign a complaint to: staff within the department."""
    from accounts.models import User

    return User.objects.filter(
        Q(department_id=complaint.department_id, role=Role.HOD) | Q(role=Role.ADMIN),
        is_active=True,
    ).order_by("full_name")
