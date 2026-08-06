"""
Email dispatch (FR-9, Algorithm 9).

Design rules, straight from the SRS:

* a failed send is logged, never raised - the user's request always succeeds;
* delivery happens on a worker thread in production so SMTP latency does not
  slow the response;
* anonymous complaints never leak identity into a mail sent to staff.
"""

import logging
import threading

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

from .models import DeliveryStatus, Notification

logger = logging.getLogger("notifications")

#: Human-readable subject lines per event.
SUBJECT_TEMPLATES = {
    "submitted": "Complaint {reference} received",
    "assigned": "Complaint {reference} has been assigned",
    "status_changed": "Complaint {reference} is now {status}",
    "remark": "New update on complaint {reference}",
}


def _deliver(notification_id, subject, body, html_body, recipient):
    """Perform the actual SMTP send and record the outcome."""
    try:
        message = EmailMultiAlternatives(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient],
        )
        if html_body:
            message.attach_alternative(html_body, "text/html")
        message.send(fail_silently=False)
    except Exception as exc:  # noqa: BLE001 - deliberately broad
        logger.error(
            "Notification %s to %s failed: %s", notification_id, recipient, exc
        )
        _mark(notification_id, DeliveryStatus.FAILED, error=str(exc))
        _record_failure_audit(notification_id, recipient, exc)
    else:
        logger.info("Notification %s delivered to %s", notification_id, recipient)
        _mark(notification_id, DeliveryStatus.SENT)


def _mark(notification_id, status, error=""):
    try:
        Notification.objects.filter(pk=notification_id).update(
            status=status,
            error=error[:2000],
            sent_at=timezone.now() if status == DeliveryStatus.SENT else None,
        )
    except Exception:  # pragma: no cover - bookkeeping must not raise
        logger.exception("Could not update notification %s", notification_id)


def _record_failure_audit(notification_id, recipient, exc):
    try:
        from accounts.models import AuditAction, AuditLog

        AuditLog.record(
            action=AuditAction.NOTIFICATION_FAILED,
            target=recipient,
            detail=f"notification={notification_id} error={exc}",
        )
    except Exception:  # pragma: no cover
        logger.exception("Could not audit notification failure")


def send_email(*, recipient, subject, body, html_body="", complaint=None, event=""):
    """
    Queue an email and return the :class:`Notification` row.

    Never raises: a caller can always treat this as fire-and-forget.
    """
    if not recipient:
        logger.warning("Skipping notification '%s' - no recipient address.", subject)
        return None

    try:
        notification = Notification.objects.create(
            complaint=complaint,
            event=event,
            recipient_email=recipient,
            subject=subject[:255],
            message=body,
            status=DeliveryStatus.PENDING,
        )
    except Exception:  # pragma: no cover
        logger.exception("Could not persist notification for %s", recipient)
        return None

    args = (notification.pk, subject, body, html_body, recipient)
    if getattr(settings, "NOTIFICATIONS_ASYNC", False):
        thread = threading.Thread(target=_deliver, args=args, daemon=True)
        thread.start()
    else:
        _deliver(*args)
    return notification


def notify_complaint_event(complaint, *, event, context=None):
    """
    Send the appropriate notification for a complaint lifecycle event.

    The complainant is always the recipient; the message body is rendered from
    ``templates/notifications/email/*`` and never contains staff-internal notes.
    """
    context = context or {}
    recipient = complaint.student.email if complaint.student_id else ""
    status_label = complaint.get_status_display()
    subject = SUBJECT_TEMPLATES.get(event, "Update on complaint {reference}").format(
        reference=complaint.reference, status=status_label
    )

    render_context = {
        "complaint": complaint,
        "event": event,
        "status_label": status_label,
        "recipient_name": complaint.student.get_short_name(),
        "portal_name": settings.PORTAL_NAME,
        "institution": settings.INSTITUTION_NAME,
        **context,
    }

    try:
        body = render_to_string("notifications/email/complaint_event.txt", render_context)
        html_body = render_to_string(
            "notifications/email/complaint_event.html", render_context
        )
    except Exception:  # pragma: no cover - template errors must not break flow
        logger.exception("Could not render notification template for %s", event)
        body = (
            f"Complaint {complaint.reference} - {status_label}.\n"
            f"Subject: {complaint.subject}"
        )
        html_body = ""

    return send_email(
        recipient=recipient,
        subject=subject,
        body=body,
        html_body=html_body,
        complaint=complaint,
        event=event,
    )
