"""
Integration tests for the complaint -> database -> email pipeline (FR-9).

The SRS requires that a failed send is logged and never breaks the request, so
those paths are exercised explicitly.
"""

from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import AuditAction, AuditLog
from complaints.models import Complaint, ComplaintCategory, ComplaintStatus
from complaints.services import add_remark, assign_complaint, change_status
from notifications.models import DeliveryStatus, Notification
from notifications.services import notify_complaint_event, send_email

from .factories import make_admin, make_complaint, make_department, make_hod, make_student


class CommitCallbackMixin:
    """
    Notifications are dispatched from ``transaction.on_commit`` so that a
    rolled-back request never emails anyone. ``TestCase`` wraps each test in a
    transaction that never commits, so the callbacks must be run explicitly.
    """

    def commit(self):
        return self.captureOnCommitCallbacks(execute=True)


class NotificationPipelineTests(CommitCallbackMixin, TestCase):
    """Complaint action -> DB row -> outbox, end to end."""

    def setUp(self):
        mail.outbox = []
        self.department = make_department()
        self.student = make_student(
            email="pipeline.student@test.local", department=self.department
        )
        self.hod = make_hod(email="pipeline.hod@test.local", department=self.department)

    def _submit(self):
        self.client.force_login(self.student)
        with self.commit():
            self.client.post(
                reverse("complaints:create"),
                {
                    "subject": "Laboratory equipment is unusable",
                    "category": ComplaintCategory.ACADEMIC,
                    "department": self.department.pk,
                    "description": "Several workstations in the laboratory cannot boot at all.",
                },
            )
        return Complaint.objects.get()

    def test_submission_stores_the_complaint_and_sends_confirmation(self):
        complaint = self._submit()

        self.assertEqual(Complaint.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

        message = mail.outbox[0]
        self.assertEqual(message.to, [self.student.email])
        self.assertIn(complaint.reference, message.subject)
        self.assertIn(complaint.reference, message.body)

    def test_submission_records_a_notification_row(self):
        complaint = self._submit()
        notification = Notification.objects.get()
        self.assertEqual(notification.complaint, complaint)
        self.assertEqual(notification.recipient_email, self.student.email)
        self.assertEqual(notification.status, DeliveryStatus.SENT)
        self.assertTrue(notification.delivered)
        self.assertIsNotNone(notification.sent_at)

    def test_every_status_change_sends_a_notification(self):
        complaint = self._submit()
        mail.outbox = []

        for status in [
            ComplaintStatus.ASSIGNED,
            ComplaintStatus.IN_PROGRESS,
            ComplaintStatus.RESOLVED,
            ComplaintStatus.CLOSED,
        ]:
            with self.commit():
                change_status(complaint=complaint, new_status=status, actor=self.hod)

        self.assertEqual(len(mail.outbox), 4)
        self.assertIn("In Progress", mail.outbox[1].subject)

    def test_status_email_mentions_the_previous_status(self):
        complaint = self._submit()
        mail.outbox = []
        with self.commit():
            change_status(
                complaint=complaint, new_status=ComplaintStatus.ASSIGNED, actor=self.hod
            )
        self.assertIn("Submitted", mail.outbox[0].body)

    def test_assignment_sends_a_notification(self):
        complaint = self._submit()
        mail.outbox = []
        with self.commit():
            assign_complaint(complaint=complaint, assignee=self.hod, actor=self.hod)
        self.assertEqual(len(mail.outbox), 1)

    def test_public_remark_notifies_the_student(self):
        complaint = self._submit()
        mail.outbox = []
        with self.commit():
            add_remark(
                complaint=complaint,
                author=self.hod,
                text="Maintenance has been scheduled for Monday.",
            )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Maintenance has been scheduled", mail.outbox[0].body)

    def test_internal_note_does_not_notify_the_student(self):
        complaint = self._submit()
        mail.outbox = []
        with self.commit():
            add_remark(
                complaint=complaint,
                author=self.hod,
                text="Internal: chase the vendor.",
                is_internal=True,
            )
        self.assertEqual(len(mail.outbox), 0)

    def test_students_own_remark_does_not_email_themselves(self):
        complaint = self._submit()
        mail.outbox = []
        with self.commit():
            add_remark(
                complaint=complaint, author=self.student, text="Any update please?"
            )
        self.assertEqual(len(mail.outbox), 0)

    def test_anonymous_complaint_still_notifies_the_complainant(self):
        complaint = make_complaint(
            student=self.student, department=self.department, is_anonymous=True
        )
        mail.outbox = []
        notify_complaint_event(complaint, event="submitted")
        self.assertEqual(mail.outbox[0].to, [self.student.email])

    def test_notification_body_never_leaks_identity_to_a_third_party(self):
        """The mail only ever goes to the complainant, so no masking is required,
        but the recipient list must never widen to staff."""
        complaint = make_complaint(
            student=self.student, department=self.department, is_anonymous=True
        )
        mail.outbox = []
        with self.commit():
            change_status(
                complaint=complaint, new_status=ComplaintStatus.ASSIGNED, actor=self.hod
            )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.student.email])
        self.assertNotIn(self.hod.email, mail.outbox[0].to)

    def test_email_has_an_html_alternative(self):
        self._submit()
        self.assertTrue(mail.outbox[0].alternatives)
        html, mimetype = mail.outbox[0].alternatives[0]
        self.assertEqual(mimetype, "text/html")
        self.assertIn("<html", html.lower())


class NotificationFailureTests(TestCase):
    """A broken SMTP server must never break complaint handling."""

    def setUp(self):
        mail.outbox = []
        self.department = make_department()
        self.student = make_student(department=self.department)
        self.hod = make_hod(email="fail.hod@test.local", department=self.department)
        self.complaint = make_complaint(
            student=self.student, department=self.department
        )

    def test_send_failure_is_recorded_not_raised(self):
        with mock.patch(
            "notifications.services.EmailMultiAlternatives.send",
            side_effect=OSError("SMTP server unreachable"),
        ):
            notification = notify_complaint_event(self.complaint, event="submitted")

        notification.refresh_from_db()
        self.assertEqual(notification.status, DeliveryStatus.FAILED)
        self.assertIn("SMTP server unreachable", notification.error)

    def test_send_failure_is_audited(self):
        AuditLog.objects.all().delete()
        with mock.patch(
            "notifications.services.EmailMultiAlternatives.send",
            side_effect=OSError("SMTP down"),
        ):
            notify_complaint_event(self.complaint, event="submitted")
        self.assertTrue(
            AuditLog.objects.filter(action=AuditAction.NOTIFICATION_FAILED).exists()
        )

    def test_submission_still_succeeds_when_email_fails(self):
        self.client.force_login(self.student)
        with mock.patch(
            "notifications.services.EmailMultiAlternatives.send",
            side_effect=OSError("SMTP down"),
        ), self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("complaints:create"),
                {
                    "subject": "A complaint filed while email is broken",
                    "category": ComplaintCategory.OTHER,
                    "department": self.department.pk,
                    "description": "The mail server is down but this must still save.",
                },
            )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Complaint.objects.filter(
                subject="A complaint filed while email is broken"
            ).exists()
        )

    def test_status_change_still_succeeds_when_email_fails(self):
        with mock.patch(
            "notifications.services.EmailMultiAlternatives.send",
            side_effect=OSError("SMTP down"),
        ), self.captureOnCommitCallbacks(execute=True):
            change_status(
                complaint=self.complaint,
                new_status=ComplaintStatus.ASSIGNED,
                actor=self.hod,
            )
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, ComplaintStatus.ASSIGNED)

    def test_missing_recipient_is_skipped_without_error(self):
        self.assertIsNone(
            send_email(recipient="", subject="No one", body="body")
        )
        self.assertEqual(Notification.objects.count(), 0)

    def test_broken_template_falls_back_to_a_plain_body(self):
        with mock.patch(
            "notifications.services.render_to_string",
            side_effect=Exception("template exploded"),
        ):
            notification = notify_complaint_event(self.complaint, event="submitted")
        self.assertIsNotNone(notification)
        self.assertIn(self.complaint.reference, notification.message)

    def test_notification_str_is_informative(self):
        notification = notify_complaint_event(self.complaint, event="submitted")
        self.assertIn(self.student.email, str(notification))


@override_settings(NOTIFICATIONS_ASYNC=True)
class AsyncDispatchTests(TestCase):
    """In async mode delivery happens off the request thread."""

    def setUp(self):
        mail.outbox = []
        self.department = make_department()
        self.student = make_student(department=self.department)
        self.complaint = make_complaint(
            student=self.student, department=self.department
        )

    def test_async_mode_spawns_a_worker_thread(self):
        with mock.patch("notifications.services.threading.Thread") as thread:
            notify_complaint_event(self.complaint, event="submitted")
            thread.assert_called_once()
            self.assertTrue(thread.call_args.kwargs["daemon"])

    def test_notification_row_exists_immediately_even_in_async_mode(self):
        with mock.patch("notifications.services.threading.Thread"):
            notification = notify_complaint_event(self.complaint, event="submitted")
        self.assertEqual(notification.status, DeliveryStatus.PENDING)


class PlainTextEmailEscapingTests(CommitCallbackMixin, TestCase):
    """
    The plain-text email body must not be HTML-escaped.

    Django autoescapes every template, including `.txt` ones. That turned the
    institution name "Online Complaint Registration & Management System" into
    "...&amp;..." in the message students actually receive, and would mangle any
    subject containing & < > or a quote.
    """

    def setUp(self):
        mail.outbox = []
        self.department = make_department()
        self.student = make_student(department=self.department)
        self.complaint = make_complaint(
            student=self.student, department=self.department
        )

    def _send(self, subject=None):
        if subject is not None:
            self.complaint.subject = subject
            self.complaint.save(update_fields=["subject"])
        notify_complaint_event(self.complaint, event="submitted")
        return mail.outbox[-1]

    def test_ampersand_is_not_escaped_in_the_plain_text_body(self):
        body = self._send().body
        self.assertNotIn("&amp;", body)
        self.assertIn("Complaint Registration & Management System", body)

    def test_special_characters_in_a_subject_survive_intact(self):
        body = self._send('Fees & "late" charges <urgent>').body
        self.assertIn('Fees & "late" charges <urgent>', body)
        for entity in ("&amp;", "&quot;", "&lt;", "&gt;", "&#x27;"):
            self.assertNotIn(entity, body)

    def test_html_alternative_is_still_escaped(self):
        """The HTML part must keep escaping - only the text part changes."""
        message = self._send("Fees & charges")
        html = next(
            content
            for content, mimetype in message.alternatives
            if mimetype == "text/html"
        )
        self.assertIn("Fees &amp; charges", html)
