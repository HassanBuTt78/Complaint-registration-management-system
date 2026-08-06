"""
Functional tests for the complaint lifecycle.

Covers FR-3 (submission), FR-4 (attachments), FR-5 (anonymity), FR-6 (tracking)
and FR-8 (status updates), plus Algorithms 3, 4, 6, 7, 8 and 10.
"""

import shutil
import tempfile

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import AuditAction, AuditLog
from complaints.categorizer import suggest_category, suggest_department
from complaints.forms import ComplaintForm, StatusUpdateForm
from complaints.models import (
    Complaint,
    ComplaintCategory,
    ComplaintRemark,
    ComplaintStatus,
)
from complaints.services import apply_filters
from complaints.validators import validate_attachment

from .factories import (
    PASSWORD,
    disguised_upload,
    executable_upload,
    make_admin,
    make_complaint,
    make_department,
    make_hod,
    make_student,
    oversized_upload,
    pdf_upload,
    png_upload,
)

MEDIA_ROOT = tempfile.mkdtemp(prefix="ocr-test-media-")


class ComplaintBaseTestCase(TestCase):
    """Shared cast of characters for the complaint tests."""

    @classmethod
    def setUpTestData(cls):
        cls.it = make_department()
        cls.hostel = make_department(name="Hostel & Student Affairs", code="HSA")
        cls.student = make_student(
            email="student@test.local",
            department=cls.it,
            full_name="Abdul Wahab",
            identifier="BSIT-084600",
        )
        cls.other_student = make_student(
            email="other@test.local", department=cls.it, full_name="Mohsin Ali"
        )
        cls.it_hod = make_hod(
            email="it.hod@test.local", department=cls.it, full_name="Haseeb Azmat"
        )
        cls.hostel_hod = make_hod(
            email="hostel.hod@test.local", department=cls.hostel, full_name="Nadia Iqbal"
        )
        cls.admin = make_admin(email="principal@test.local", full_name="The Principal")


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class ComplaintSubmissionTests(ComplaintBaseTestCase):
    """FR-3 / FR-4: submission and attachments."""

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.url = reverse("complaints:create")
        self.client.force_login(self.student)

    def _payload(self, **overrides):
        payload = {
            "subject": "Projector in room 14 is broken",
            "category": ComplaintCategory.ACADEMIC,
            "department": self.it.pk,
            "description": "The projector has not worked for two weeks and lectures "
            "cannot be followed properly.",
        }
        payload.update(overrides)
        return payload

    def test_form_page_renders(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Submit a New Complaint")

    def test_valid_submission_creates_complaint(self):
        response = self.client.post(self.url, self._payload())
        complaint = Complaint.objects.get(subject="Projector in room 14 is broken")
        self.assertRedirects(response, complaint.get_absolute_url())
        self.assertEqual(complaint.student, self.student)
        self.assertEqual(complaint.status, ComplaintStatus.SUBMITTED)
        self.assertFalse(complaint.is_anonymous)

    def test_submission_writes_audit_entry(self):
        self.client.post(self.url, self._payload())
        self.assertTrue(
            AuditLog.objects.filter(action=AuditAction.COMPLAINT_CREATED).exists()
        )

    def test_submission_creates_initial_history_row(self):
        self.client.post(self.url, self._payload())
        complaint = Complaint.objects.get(subject="Projector in room 14 is broken")
        self.assertEqual(complaint.status_history.count(), 1)

    def test_anonymous_submission_sets_the_flag_but_keeps_the_student(self):
        self.client.post(self.url, self._payload(is_anonymous="on"))
        complaint = Complaint.objects.get(subject="Projector in room 14 is broken")
        self.assertTrue(complaint.is_anonymous)
        self.assertEqual(complaint.student, self.student)  # stored internally

    def test_empty_submission_is_rejected(self):
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Complaint.objects.count(), 0)

    def test_short_subject_is_rejected(self):
        response = self.client.post(self.url, self._payload(subject="Hi"))
        self.assertContains(response, "at least 5 characters")
        self.assertEqual(Complaint.objects.count(), 0)

    def test_short_description_is_rejected(self):
        response = self.client.post(self.url, self._payload(description="Broken"))
        self.assertContains(response, "at least 20 characters")

    def test_missing_department_is_rejected(self):
        response = self.client.post(self.url, self._payload(department=""))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Complaint.objects.count(), 0)

    def test_png_attachment_is_accepted(self):
        payload = self._payload()
        payload["attachments"] = png_upload()
        self.client.post(self.url, payload)
        complaint = Complaint.objects.get()
        self.assertEqual(complaint.attachments.count(), 1)
        attachment = complaint.attachments.get()
        self.assertEqual(attachment.original_name, "evidence.png")
        self.assertGreater(attachment.size_bytes, 0)

    def test_pdf_attachment_is_accepted(self):
        payload = self._payload()
        payload["attachments"] = pdf_upload()
        self.client.post(self.url, payload)
        self.assertEqual(Complaint.objects.get().attachments.count(), 1)

    def test_executable_attachment_is_rejected(self):
        payload = self._payload()
        payload["attachments"] = executable_upload()
        response = self.client.post(self.url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Complaint.objects.count(), 0)

    def test_renamed_executable_is_rejected_by_magic_number(self):
        payload = self._payload()
        payload["attachments"] = disguised_upload()
        response = self.client.post(self.url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "does not match a valid")
        self.assertEqual(Complaint.objects.count(), 0)

    def test_oversized_attachment_is_rejected(self):
        payload = self._payload()
        payload["attachments"] = oversized_upload()
        response = self.client.post(self.url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Complaint.objects.count(), 0)

    def test_hod_cannot_submit_a_complaint(self):
        self.client.force_login(self.it_hod)
        response = self.client.post(self.url, self._payload())
        self.assertEqual(response.status_code, 403)

    def test_anonymous_visitor_is_redirected_to_login(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)


class AttachmentValidatorTests(TestCase):
    """Direct unit tests of the upload validator (FR-4 business rule)."""

    def test_accepts_png_and_pdf(self):
        self.assertIsNotNone(validate_attachment(png_upload()))
        self.assertIsNotNone(validate_attachment(pdf_upload()))

    def test_rejects_disallowed_extension(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_attachment(executable_upload())
        self.assertIn("Unsupported file type", str(ctx.exception))

    def test_rejects_oversized_file(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_attachment(oversized_upload())
        self.assertIn("too large", str(ctx.exception))

    def test_rejects_content_type_mismatch(self):
        with self.assertRaises(ValidationError):
            validate_attachment(disguised_upload())

    def test_rejects_empty_file(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        with self.assertRaises(ValidationError):
            validate_attachment(
                SimpleUploadedFile("empty.png", b"", content_type="image/png")
            )

    def test_none_is_passed_through(self):
        self.assertIsNone(validate_attachment(None))


class ComplaintEditTests(ComplaintBaseTestCase):
    """UC5: editable only before assignment."""

    def setUp(self):
        self.complaint = make_complaint(student=self.student, department=self.it)
        self.url = reverse("complaints:edit", args=[self.complaint.pk])
        self.client.force_login(self.student)

    def test_owner_can_edit_while_submitted(self):
        response = self.client.post(
            self.url,
            {
                "subject": "Updated subject line for the projector",
                "category": ComplaintCategory.ACADEMIC,
                "department": self.it.pk,
                "description": "An updated description that is definitely long enough.",
            },
        )
        self.assertRedirects(response, self.complaint.get_absolute_url())
        self.complaint.refresh_from_db()
        self.assertEqual(
            self.complaint.subject, "Updated subject line for the projector"
        )

    def test_edit_after_assignment_is_forbidden(self):
        self.complaint.transition_to(ComplaintStatus.ASSIGNED, actor=self.it_hod)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_other_student_cannot_edit(self):
        self.client.force_login(self.other_student)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)

    def test_hod_cannot_edit_a_students_complaint(self):
        self.client.force_login(self.it_hod)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_owner_can_cancel_before_assignment(self):
        response = self.client.post(reverse("complaints:cancel", args=[self.complaint.pk]))
        self.assertRedirects(response, self.complaint.get_absolute_url())
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, ComplaintStatus.CANCELLED)

    def test_cancel_after_assignment_is_forbidden(self):
        self.complaint.transition_to(ComplaintStatus.ASSIGNED, actor=self.it_hod)
        response = self.client.post(reverse("complaints:cancel", args=[self.complaint.pk]))
        self.assertEqual(response.status_code, 403)
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, ComplaintStatus.ASSIGNED)


class StatusUpdateViewTests(ComplaintBaseTestCase):
    """FR-8: HOD status updates constrained by the state machine."""

    def setUp(self):
        self.complaint = make_complaint(student=self.student, department=self.it)
        self.url = reverse("complaints:status", args=[self.complaint.pk])

    def test_hod_can_advance_the_status(self):
        self.client.force_login(self.it_hod)
        response = self.client.post(
            self.url, {"status": ComplaintStatus.ASSIGNED, "note": "Taken up"}
        )
        self.assertRedirects(response, self.complaint.get_absolute_url())
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, ComplaintStatus.ASSIGNED)

    def test_status_change_is_audited(self):
        self.client.force_login(self.it_hod)
        self.client.post(self.url, {"status": ComplaintStatus.ASSIGNED})
        self.assertTrue(
            AuditLog.objects.filter(
                action=AuditAction.COMPLAINT_STATUS_CHANGED
            ).exists()
        )

    def test_illegal_transition_is_rejected_by_the_view(self):
        self.client.force_login(self.it_hod)
        response = self.client.post(
            self.url, {"status": ComplaintStatus.CLOSED}, follow=True
        )
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, ComplaintStatus.SUBMITTED)
        self.assertContains(response, "Invalid status update")

    def test_hod_of_another_department_is_forbidden(self):
        self.client.force_login(self.hostel_hod)
        response = self.client.post(self.url, {"status": ComplaintStatus.ASSIGNED})
        self.assertEqual(response.status_code, 404)
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, ComplaintStatus.SUBMITTED)

    def test_student_cannot_change_status(self):
        self.client.force_login(self.student)
        response = self.client.post(self.url, {"status": ComplaintStatus.ASSIGNED})
        self.assertEqual(response.status_code, 403)

    def test_admin_can_change_status_of_any_department(self):
        self.client.force_login(self.admin)
        self.client.post(self.url, {"status": ComplaintStatus.ASSIGNED})
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, ComplaintStatus.ASSIGNED)

    def test_form_only_offers_legal_next_statuses(self):
        form = StatusUpdateForm(complaint=self.complaint)
        offered = {value for value, _label in form.fields["status"].choices}
        self.assertEqual(
            offered, {ComplaintStatus.ASSIGNED, ComplaintStatus.CANCELLED}
        )


class AssignmentTests(ComplaintBaseTestCase):
    """UC10: assignment moves the complaint to Assigned."""

    def setUp(self):
        self.complaint = make_complaint(student=self.student, department=self.it)
        self.url = reverse("complaints:assign", args=[self.complaint.pk])

    def test_hod_can_assign_and_status_advances(self):
        self.client.force_login(self.it_hod)
        response = self.client.post(self.url, {"assigned_to": self.it_hod.pk})
        self.assertRedirects(response, self.complaint.get_absolute_url())
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.assigned_to, self.it_hod)
        self.assertEqual(self.complaint.status, ComplaintStatus.ASSIGNED)

    def test_assignment_is_audited(self):
        self.client.force_login(self.it_hod)
        self.client.post(self.url, {"assigned_to": self.it_hod.pk})
        self.assertTrue(
            AuditLog.objects.filter(action=AuditAction.COMPLAINT_ASSIGNED).exists()
        )

    def test_cannot_assign_a_foreign_department_staff_member(self):
        self.client.force_login(self.it_hod)
        response = self.client.post(self.url, {"assigned_to": self.hostel_hod.pk}, follow=True)
        self.complaint.refresh_from_db()
        self.assertIsNone(self.complaint.assigned_to_id)
        self.assertContains(response, "Could not assign")

    def test_student_cannot_assign(self):
        self.client.force_login(self.student)
        response = self.client.post(self.url, {"assigned_to": self.it_hod.pk})
        self.assertEqual(response.status_code, 403)


class RemarkTests(ComplaintBaseTestCase):
    """UC12: remarks, including the internal-note rule."""

    def setUp(self):
        self.complaint = make_complaint(student=self.student, department=self.it)
        self.url = reverse("complaints:remark", args=[self.complaint.pk])

    def test_hod_can_add_a_remark(self):
        self.client.force_login(self.it_hod)
        self.client.post(self.url, {"text": "We have escalated this to maintenance."})
        self.assertEqual(self.complaint.remarks.count(), 1)

    def test_student_can_reply(self):
        self.client.force_login(self.student)
        self.client.post(self.url, {"text": "Thank you, any update?"})
        self.assertEqual(self.complaint.remarks.count(), 1)

    def test_student_cannot_create_an_internal_note(self):
        self.client.force_login(self.student)
        self.client.post(self.url, {"text": "Sneaky internal note", "is_internal": "on"})
        self.assertFalse(self.complaint.remarks.get().is_internal)

    def test_internal_notes_are_hidden_from_the_student(self):
        ComplaintRemark.objects.create(
            complaint=self.complaint,
            author=self.it_hod,
            text="Internal: escalate to the Principal.",
            is_internal=True,
        )
        visible = ComplaintRemark.objects.visible_to(self.student, self.complaint)
        self.assertEqual(visible.count(), 0)
        self.assertEqual(
            ComplaintRemark.objects.visible_to(self.it_hod, self.complaint).count(), 1
        )

    def test_internal_note_is_absent_from_the_students_detail_page(self):
        ComplaintRemark.objects.create(
            complaint=self.complaint,
            author=self.it_hod,
            text="INTERNALSECRETNOTE",
            is_internal=True,
        )
        self.client.force_login(self.student)
        response = self.client.get(self.complaint.get_absolute_url())
        self.assertNotContains(response, "INTERNALSECRETNOTE")

    def test_short_remark_is_rejected(self):
        self.client.force_login(self.it_hod)
        self.client.post(self.url, {"text": "ok"})
        self.assertEqual(self.complaint.remarks.count(), 0)

    def test_remark_on_foreign_complaint_is_not_found(self):
        self.client.force_login(self.hostel_hod)
        response = self.client.post(self.url, {"text": "Trying to comment here."})
        self.assertEqual(response.status_code, 404)


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class AttachmentDownloadTests(ComplaintBaseTestCase):
    """Media is only reachable through the permission-checked view."""

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.complaint = make_complaint(student=self.student, department=self.it)
        self.attachment = self.complaint.attachments.create(
            file=png_upload(), original_name="evidence.png", content_type="image/png",
            size_bytes=100,
        )
        self.url = reverse("complaints:attachment", args=[self.attachment.pk])

    def test_owner_can_download(self):
        self.client.force_login(self.student)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")

    def test_owning_department_hod_can_download(self):
        self.client.force_login(self.it_hod)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_foreign_hod_is_forbidden(self):
        self.client.force_login(self.hostel_hod)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_other_student_is_forbidden(self):
        self.client.force_login(self.other_student)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_unauthenticated_visitor_is_forbidden(self):
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_blocked_download_is_audited(self):
        self.client.force_login(self.other_student)
        self.client.get(self.url)
        self.assertTrue(
            AuditLog.objects.filter(action=AuditAction.ACCESS_DENIED).exists()
        )


class FilterAndSearchTests(ComplaintBaseTestCase):
    """Algorithms 5, 7 and 8: role-aware filtering, search and sorting."""

    def setUp(self):
        self.a = make_complaint(
            student=self.student,
            department=self.it,
            subject="Laboratory projector needs replacing",
            description="The teaching equipment in lab two has failed completely.",
            category=ComplaintCategory.ACADEMIC,
        )
        self.b = make_complaint(
            student=self.other_student,
            department=self.it,
            subject="Hostel mess food quality has dropped",
            description="Meals served in the residence block are of poor quality.",
            category=ComplaintCategory.HOSTEL,
            status=ComplaintStatus.ASSIGNED,
        )

    def _filter(self, user, **data):
        return apply_filters(
            Complaint.objects.visible_to(user), cleaned_data=data, user=user
        )

    def test_keyword_search_matches_subject(self):
        results = self._filter(self.admin, q="projector")
        self.assertEqual(list(results), [self.a])

    def test_keyword_search_matches_reference(self):
        results = self._filter(self.admin, q=self.b.reference)
        self.assertEqual(list(results), [self.b])

    def test_status_filter(self):
        self.assertEqual(
            list(self._filter(self.admin, status=ComplaintStatus.ASSIGNED)), [self.b]
        )

    def test_category_filter(self):
        self.assertEqual(
            list(self._filter(self.admin, category=ComplaintCategory.HOSTEL)), [self.b]
        )

    def test_date_range_filter(self):
        from django.utils import timezone

        today = timezone.localdate()
        self.assertEqual(self._filter(self.admin, date_from=today).count(), 2)
        self.assertEqual(
            self._filter(
                self.admin, date_to=today - timezone.timedelta(days=1)
            ).count(),
            0,
        )

    def test_sorting_is_restricted_to_a_safe_allowlist(self):
        """An injected sort key falls back to the default ordering."""
        results = self._filter(self.admin, sort="student__password")
        self.assertEqual(list(results), [self.b, self.a])  # newest first

    def test_admin_can_search_named_complainants(self):
        self.assertEqual(list(self._filter(self.admin, q="Abdul Wahab")), [self.a])

    def test_admin_search_never_matches_anonymous_complainants(self):
        anonymous = make_complaint(
            student=self.student,
            department=self.it,
            subject="A sensitive anonymous report",
            is_anonymous=True,
        )
        results = self._filter(self.admin, q="Abdul Wahab")
        self.assertNotIn(anonymous, results)

    def test_hod_search_cannot_match_complainant_names(self):
        """An HOD probing for a student name must get nothing back."""
        results = self._filter(self.it_hod, q="Abdul Wahab")
        self.assertEqual(results.count(), 0)

    def test_hod_search_stays_within_the_department(self):
        make_complaint(
            student=self.student,
            department=self.hostel,
            subject="Projector missing in the hostel study room",
            description="The study room screen equipment has disappeared entirely.",
        )
        results = self._filter(self.it_hod, q="projector")
        self.assertEqual(list(results), [self.a])


class CategorizerTests(TestCase):
    """Bonus rule-based categoriser."""

    def test_academic_keywords(self):
        category, confidence = suggest_category(
            "My exam marks and grade for the assignment are wrong"
        )
        self.assertEqual(category, ComplaintCategory.ACADEMIC.value)
        self.assertGreater(confidence, 0)

    def test_hostel_keywords(self):
        category, _ = suggest_category("The hostel mess food and warden are a problem")
        self.assertEqual(category, ComplaintCategory.HOSTEL.value)

    def test_administration_keywords(self):
        category, _ = suggest_category("My fee challan and admission certificate")
        self.assertEqual(category, ComplaintCategory.ADMINISTRATION.value)

    def test_unmatched_text_returns_other(self):
        category, confidence = suggest_category("qwerty zxcvb asdfg")
        self.assertEqual(category, ComplaintCategory.OTHER.value)
        self.assertEqual(confidence, 0.0)

    def test_empty_text_returns_other(self):
        self.assertEqual(suggest_category("")[0], ComplaintCategory.OTHER.value)

    def test_department_suggestion_matches_by_name(self):
        it = make_department()
        hostel = make_department(name="Hostel & Student Affairs", code="HSA")
        suggestion = suggest_department(
            "Problem with the Information Technology lab", [it, hostel]
        )
        self.assertEqual(suggestion, it)

    def test_department_suggestion_returns_none_when_unmatched(self):
        it = make_department()
        self.assertIsNone(suggest_department("zzz qqq", [it]))

    def test_suggest_endpoint_returns_json(self):
        department = make_department()
        student = make_student(department=department)
        self.client.force_login(student)
        response = self.client.get(
            reverse("complaints:suggest"),
            {"subject": "Hostel mess", "description": "The warden ignores the mess food complaints"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["category"], ComplaintCategory.HOSTEL.value)
        self.assertIn("confidence", payload)


class ComplaintFormUnitTests(ComplaintBaseTestCase):
    def test_form_assigns_the_student_on_save(self):
        form = ComplaintForm(
            data={
                "subject": "A valid subject line",
                "category": ComplaintCategory.OTHER,
                "department": self.it.pk,
                "description": "A description that comfortably exceeds twenty chars.",
            },
            student=self.student,
        )
        self.assertTrue(form.is_valid(), form.errors)
        complaint = form.save()
        self.assertEqual(complaint.student, self.student)

    def test_more_than_five_attachments_are_rejected(self):
        from complaints.forms import MultipleFileField

        field = MultipleFileField(required=False)
        with self.assertRaises(ValidationError):
            field.clean([png_upload(f"f{i}.png") for i in range(6)])

    def test_empty_attachment_list_is_allowed(self):
        from complaints.forms import MultipleFileField

        self.assertEqual(MultipleFileField(required=False).clean([]), [])
