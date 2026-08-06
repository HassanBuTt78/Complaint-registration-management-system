"""Notification records: every email the system attempts to send (FR-9)."""

from django.db import models
from django.utils.translation import gettext_lazy as _


class DeliveryStatus(models.TextChoices):
    PENDING = "PENDING", _("Pending")
    SENT = "SENT", _("Sent")
    FAILED = "FAILED", _("Failed")
    SUPPRESSED = "SUPPRESSED", _("Suppressed")


class NotificationEvent(models.TextChoices):
    SUBMITTED = "submitted", _("Complaint submitted")
    ASSIGNED = "assigned", _("Complaint assigned")
    STATUS_CHANGED = "status_changed", _("Status changed")
    REMARK = "remark", _("Remark added")


class Notification(models.Model):
    """
    One row per outbound message.

    Failures are recorded here (and in the application log) instead of being
    raised, so a broken SMTP server can never break complaint handling.
    """

    complaint = models.ForeignKey(
        "complaints.Complaint",
        related_name="notifications",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    event = models.CharField(
        max_length=32, choices=NotificationEvent.choices, blank=True
    )
    recipient_email = models.EmailField(_("recipient"))
    subject = models.CharField(max_length=255)
    message = models.TextField()
    status = models.CharField(
        max_length=12, choices=DeliveryStatus.choices, default=DeliveryStatus.PENDING
    )
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = _("notification")
        verbose_name_plural = _("notifications")
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self):
        return f"{self.recipient_email}: {self.subject} [{self.status}]"

    @property
    def delivered(self):
        return self.status == DeliveryStatus.SENT
