"""
Complaint use-cases.

Views stay thin; every state-changing operation lives here so the audit trail
and the notification pipeline can never be bypassed.
"""

import logging

from django.db import transaction
from django.db.models import Q

from accounts.models import AuditAction, AuditLog

from .models import (
    Complaint,
    ComplaintAttachment,
    ComplaintRemark,
    ComplaintStatus,
    ComplaintStatusHistory,
)

logger = logging.getLogger(__name__)


def _notify(*args, **kwargs):
    """Import lazily to avoid a circular import at module load time."""
    from notifications.services import notify_complaint_event

    return notify_complaint_event(*args, **kwargs)


@transaction.atomic
def create_complaint(*, complaint, student, attachments=None, request=None):
    """Persist a new complaint plus attachments, then notify (Algorithm 3)."""
    complaint.student = student
    complaint.status = ComplaintStatus.SUBMITTED
    complaint.save()

    for uploaded in attachments or []:
        ComplaintAttachment.objects.create(
            complaint=complaint,
            file=uploaded,
            original_name=(uploaded.name or "")[:255],
            content_type=(getattr(uploaded, "content_type", "") or "")[:100],
            size_bytes=getattr(uploaded, "size", 0) or 0,
        )

    ComplaintStatusHistory.objects.create(
        complaint=complaint,
        from_status=ComplaintStatus.SUBMITTED,
        to_status=ComplaintStatus.SUBMITTED,
        changed_by=student,
        note="Complaint submitted.",
    )

    AuditLog.record(
        actor=student,
        action=AuditAction.COMPLAINT_CREATED,
        target=complaint.reference,
        detail=(
            f"category={complaint.category} department={complaint.department.name} "
            f"anonymous={complaint.is_anonymous}"
        ),
        request=request,
    )

    transaction.on_commit(lambda: _notify(complaint, event="submitted"))
    return complaint


@transaction.atomic
def update_complaint(*, complaint, actor, attachments=None, request=None):
    """Save a student's edit (only legal before assignment - UC5)."""
    complaint.save()
    for uploaded in attachments or []:
        ComplaintAttachment.objects.create(
            complaint=complaint,
            file=uploaded,
            original_name=(uploaded.name or "")[:255],
            content_type=(getattr(uploaded, "content_type", "") or "")[:100],
            size_bytes=getattr(uploaded, "size", 0) or 0,
        )
    AuditLog.record(
        actor=actor,
        action=AuditAction.COMPLAINT_UPDATED,
        target=complaint.reference,
        request=request,
    )
    return complaint


@transaction.atomic
def change_status(*, complaint, new_status, actor, note="", request=None):
    """
    Apply a validated state transition (FR-8, Algorithm 4 / 10).

    Raises ``InvalidTransition`` for illegal moves; the caller surfaces it as a
    form error.
    """
    previous = complaint.status
    complaint.transition_to(new_status, actor=actor, note=note)

    AuditLog.record(
        actor=actor,
        action=AuditAction.COMPLAINT_STATUS_CHANGED,
        target=complaint.reference,
        detail=f"{previous} -> {new_status}. {note}".strip(),
        request=request,
    )

    transaction.on_commit(
        lambda: _notify(
            complaint, event="status_changed", context={"previous_status": previous}
        )
    )
    return complaint


@transaction.atomic
def assign_complaint(*, complaint, assignee, actor, note="", request=None):
    """
    Assign to a staff member and move ``Submitted -> Assigned`` (UC10).

    Re-assignment of an already-assigned complaint keeps the current status.
    """
    complaint.assigned_to = assignee
    complaint.save(update_fields=["assigned_to", "updated_at"])

    AuditLog.record(
        actor=actor,
        action=AuditAction.COMPLAINT_ASSIGNED,
        target=complaint.reference,
        detail=f"assigned_to={assignee.get_full_name()}",
        request=request,
    )

    if complaint.can_transition_to(ComplaintStatus.ASSIGNED):
        change_status(
            complaint=complaint,
            new_status=ComplaintStatus.ASSIGNED,
            actor=actor,
            note=note or f"Assigned to {assignee.get_full_name()}.",
            request=request,
        )
    else:
        transaction.on_commit(lambda: _notify(complaint, event="assigned"))
    return complaint


@transaction.atomic
def add_remark(*, complaint, author, text, is_internal=False, request=None):
    """Attach a remark and notify the student when it is not internal (UC12)."""
    remark = ComplaintRemark.objects.create(
        complaint=complaint, author=author, text=text, is_internal=is_internal
    )
    AuditLog.record(
        actor=author,
        action=AuditAction.REMARK_ADDED,
        target=complaint.reference,
        detail="internal" if is_internal else "visible to complainant",
        request=request,
    )
    if not is_internal and author != complaint.student:
        transaction.on_commit(
            lambda: _notify(complaint, event="remark", context={"remark": remark.text})
        )
    return remark


@transaction.atomic
def unmask_complaint(*, complaint, actor, reason="", request=None):
    """
    Reveal an anonymous complainant to the Principal/Admin (FR-5, UC18).

    The complaint itself is *not* modified - anonymity is permanent for HODs.
    Only an audit entry is written recording who looked and why.
    """
    if not actor.can_view_identities():
        raise PermissionError("Only the Principal/Administrator may unmask.")
    AuditLog.record(
        actor=actor,
        action=AuditAction.UNMASK,
        target=complaint.reference,
        detail=(
            f"Identity revealed: {complaint.student.get_full_name()} "
            f"<{complaint.student.email}>. Reason: {reason or 'not stated'}"
        ),
        request=request,
    )
    return complaint.student


def apply_filters(queryset, *, cleaned_data, user):
    """
    Translate a cleaned :class:`~complaints.forms.ComplaintFilterForm` into ORM
    filters (Algorithms 5, 7 and 8).

    Keyword search deliberately never touches complainant identity fields, so an
    HOD cannot probe for an anonymous student's name.
    """
    data = cleaned_data or {}

    query = (data.get("q") or "").strip()
    if query:
        criteria = (
            Q(subject__icontains=query)
            | Q(description__icontains=query)
            | Q(reference__icontains=query)
        )
        if query.isdigit():
            criteria |= Q(pk=int(query))
        if user.is_admin_role:
            # Only the Principal may search by complainant, and never for
            # complaints that were filed anonymously.
            criteria |= Q(student__full_name__icontains=query) & Q(is_anonymous=False)
            criteria |= Q(student__identifier__icontains=query) & Q(is_anonymous=False)
        queryset = queryset.filter(criteria)

    if data.get("status"):
        queryset = queryset.filter(status=data["status"])
    if data.get("category"):
        queryset = queryset.filter(category=data["category"])
    if data.get("department"):
        queryset = queryset.filter(department=data["department"])
    if data.get("date_from"):
        queryset = queryset.filter(created_at__date__gte=data["date_from"])
    if data.get("date_to"):
        queryset = queryset.filter(created_at__date__lte=data["date_to"])

    sort = data.get("sort") or "-created_at"
    allowed_sorts = {"-created_at", "created_at", "status", "department__name"}
    if sort not in allowed_sorts:
        sort = "-created_at"
    return queryset.order_by(sort, "-id")


def get_complaint_for(user, pk):
    """Fetch a complaint scoped to what ``user`` may see, or ``None``."""
    return (
        Complaint.objects.visible_to(user)
        .with_related()
        .filter(pk=pk)
        .first()
    )
