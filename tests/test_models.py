"""Unit tests: model behaviour, the state machine and anonymity rules."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import AuditAction, AuditLog, Department, Role, User
from complaints.models import (
    ALLOWED_TRANSITIONS,
    Complaint,
    ComplaintRemark,
    ComplaintStatus,
    InvalidTransition,
    attachment_upload_path,
)

from .factories import (
    drive_to_status,
    make_admin,
    make_complaint,
    make_department,
    make_hod,
    make_student,
)


class DepartmentModelTests(TestCase):
    def test_str_returns_name(self):
        department = make_department()
        self.assertEqual(str(department), "Information Technology")

    def test_name_and_code_are_unique(self):
        make_department()
        with self.assertRaises(Exception):
            Department.objects.create(name="Information Technology", code="IT2")


class UserModelTests(TestCase):
    def setUp(self):
        self.department = make_department()

    def test_email_is_normalised_to_lowercase(self):
        user = make_student(email="Mixed.Case@Test.Local")
        self.assertEqual(user.email, "mixed.case@test.local")

    def test_role_helper_properties(self):
        student = make_student(email="s@test.local")
        hod = make_hod(email="h@test.local", department=self.department)
        admin = make_admin(email="a@test.local")

        self.assertTrue(student.is_student)
        self.assertTrue(hod.is_hod)
        self.assertTrue(admin.is_admin_role)
        self.assertFalse(student.is_hod)
        self.assertFalse(hod.is_admin_role)

    def test_only_admin_may_view_identities(self):
        self.assertFalse(make_student(email="s2@test.local").can_view_identities())
        self.assertFalse(
            make_hod(email="h2@test.local", department=self.department).can_view_identities()
        )
        self.assertTrue(make_admin(email="a2@test.local").can_view_identities())

    def test_hod_without_department_fails_validation(self):
        user = User(
            email="orphan@test.local",
            username="orphan@test.local",
            full_name="Orphan HOD",
            role=Role.HOD,
        )
        with self.assertRaises(ValidationError) as ctx:
            user.full_clean(exclude=["password"])
        self.assertIn("department", ctx.exception.error_dict)

    def test_admin_department_is_always_cleared(self):
        admin = make_admin(email="a3@test.local")
        admin.department = self.department
        admin.save()
        admin.refresh_from_db()
        self.assertIsNone(admin.department_id)

    def test_str_includes_name_and_email(self):
        user = make_student(email="s3@test.local", full_name="Test Student")
        self.assertEqual(str(user), "Test Student <s3@test.local>")

    def test_manager_creates_superuser_with_admin_role(self):
        superuser = User.objects.create_superuser(
            email="root@test.local", password="Sup3r!Pass2026", full_name="Root"
        )
        self.assertTrue(superuser.is_superuser)
        self.assertTrue(superuser.is_staff)
        self.assertEqual(superuser.role, Role.ADMIN)

    def test_create_user_requires_email(self):
        with self.assertRaises(ValueError):
            User.objects.create_user(email="", password="x")


class ComplaintReferenceTests(TestCase):
    def setUp(self):
        self.department = make_department()
        self.student = make_student(department=self.department)

    def test_reference_is_generated_and_sequential(self):
        first = make_complaint(student=self.student, department=self.department)
        second = make_complaint(
            student=self.student, department=self.department, subject="Second issue here"
        )
        self.assertTrue(first.reference.startswith("CMP-"))
        self.assertNotEqual(first.reference, second.reference)
        self.assertLess(first.reference, second.reference)

    def test_str_and_absolute_url(self):
        complaint = make_complaint(student=self.student, department=self.department)
        self.assertIn(complaint.reference, str(complaint))
        self.assertEqual(
            complaint.get_absolute_url(), f"/complaints/{complaint.pk}/"
        )


class StateMachineTests(TestCase):
    def setUp(self):
        self.department = make_department()
        self.student = make_student(department=self.department)
        self.hod = make_hod(department=self.department)

    def _complaint(self, status=ComplaintStatus.SUBMITTED):
        return make_complaint(
            student=self.student, department=self.department, status=status
        )

    def test_happy_path_transitions_are_allowed(self):
        complaint = self._complaint()
        for status in [
            ComplaintStatus.ASSIGNED,
            ComplaintStatus.IN_PROGRESS,
            ComplaintStatus.RESOLVED,
            ComplaintStatus.CLOSED,
        ]:
            complaint.transition_to(status, actor=self.hod)
            self.assertEqual(complaint.status, status)

    def test_submitted_may_be_cancelled(self):
        complaint = self._complaint()
        complaint.transition_to(ComplaintStatus.CANCELLED, actor=self.student)
        self.assertEqual(complaint.status, ComplaintStatus.CANCELLED)

    def test_skipping_a_step_is_rejected(self):
        complaint = self._complaint()
        with self.assertRaises(InvalidTransition):
            complaint.transition_to(ComplaintStatus.RESOLVED, actor=self.hod)
        complaint.refresh_from_db()
        self.assertEqual(complaint.status, ComplaintStatus.SUBMITTED)

    def test_cannot_move_backwards(self):
        complaint = self._complaint(ComplaintStatus.IN_PROGRESS)
        with self.assertRaises(InvalidTransition):
            complaint.transition_to(ComplaintStatus.ASSIGNED, actor=self.hod)

    def test_terminal_states_are_final(self):
        for terminal in (ComplaintStatus.CLOSED, ComplaintStatus.CANCELLED):
            complaint = self._complaint(terminal)
            self.assertEqual(complaint.allowed_next_statuses, [])
            for target in ComplaintStatus.values:
                if target == terminal:
                    continue
                with self.assertRaises(InvalidTransition):
                    complaint.transition_to(target, actor=self.hod)

    def test_transition_to_same_status_is_rejected(self):
        complaint = self._complaint()
        with self.assertRaises(InvalidTransition):
            complaint.transition_to(ComplaintStatus.SUBMITTED, actor=self.hod)

    def test_unknown_status_is_rejected(self):
        complaint = self._complaint()
        with self.assertRaises(InvalidTransition):
            complaint.transition_to("TELEPORTED", actor=self.hod)

    def test_every_illegal_pair_is_refused(self):
        """Exhaustive sweep over the full status x status matrix."""
        for source in ComplaintStatus.values:
            for target in ComplaintStatus.values:
                if target in ALLOWED_TRANSITIONS[source]:
                    continue
                complaint = self._complaint(source)
                with self.assertRaises(InvalidTransition):
                    complaint.transition_to(target, actor=self.hod)

    def test_transition_writes_history(self):
        complaint = self._complaint()
        complaint.transition_to(
            ComplaintStatus.ASSIGNED, actor=self.hod, note="Handled by IT"
        )
        history = complaint.status_history.last()
        self.assertEqual(history.from_status, ComplaintStatus.SUBMITTED)
        self.assertEqual(history.to_status, ComplaintStatus.ASSIGNED)
        self.assertEqual(history.changed_by, self.hod)
        self.assertEqual(history.note, "Handled by IT")

    def test_resolved_and_closed_timestamps_are_stamped(self):
        complaint = self._complaint(ComplaintStatus.RESOLVED)
        self.assertIsNotNone(complaint.resolved_at)
        self.assertIsNotNone(complaint.resolution_hours)
        complaint.transition_to(ComplaintStatus.CLOSED, actor=self.hod)
        self.assertIsNotNone(complaint.closed_at)

    def test_resolution_hours_is_none_while_unresolved(self):
        self.assertIsNone(self._complaint().resolution_hours)

    def test_editable_only_while_submitted(self):
        self.assertTrue(self._complaint().is_editable)
        self.assertFalse(self._complaint(ComplaintStatus.ASSIGNED).is_editable)

    def test_can_be_edited_by_owner_only(self):
        complaint = self._complaint()
        other = make_student(email="other@test.local", department=self.department)
        self.assertTrue(complaint.can_be_edited_by(self.student))
        self.assertFalse(complaint.can_be_edited_by(other))
        self.assertFalse(complaint.can_be_edited_by(self.hod))


class AnonymityTests(TestCase):
    def setUp(self):
        self.it = make_department()
        self.hostel = make_department(name="Hostel", code="HSA")
        self.student = make_student(
            department=self.it, full_name="Abdul Wahab", identifier="BSIT-084600"
        )
        self.hod = make_hod(department=self.it)
        self.admin = make_admin()
        self.anon = make_complaint(
            student=self.student, department=self.it, is_anonymous=True
        )
        self.named = make_complaint(
            student=self.student,
            department=self.it,
            is_anonymous=False,
            subject="A named complaint about lab access",
        )

    def test_hod_cannot_see_anonymous_identity(self):
        self.assertFalse(self.anon.identity_visible_to(self.hod))
        self.assertNotIn("Abdul", self.anon.complainant_display(self.hod))
        self.assertEqual(self.anon.complainant_identifier(self.hod), "-")
        self.assertEqual(self.anon.complainant_email(self.hod), "-")

    def test_admin_identity_is_masked_until_explicitly_unmasked(self):
        """The Principal's privilege is the audited unmask action, not passive sight."""
        self.assertFalse(self.anon.identity_visible_to(self.admin))
        self.assertNotIn("Abdul", self.anon.complainant_display(self.admin))
        self.assertTrue(self.anon.can_unmask(self.admin))

    def test_only_admin_can_unmask(self):
        self.assertFalse(self.anon.can_unmask(self.hod))
        self.assertFalse(self.anon.can_unmask(self.student))
        self.assertTrue(self.anon.can_unmask(self.admin))

    def test_named_complaints_are_never_unmaskable(self):
        self.assertFalse(self.named.can_unmask(self.admin))

    def test_owner_always_sees_own_identity(self):
        self.assertTrue(self.anon.identity_visible_to(self.student))
        self.assertEqual(self.anon.complainant_display(self.student), "Abdul Wahab")

    def test_other_student_cannot_see_identity(self):
        other = make_student(email="other@test.local", department=self.it)
        self.assertFalse(self.anon.identity_visible_to(other))

    def test_named_complaint_is_visible_to_hod(self):
        self.assertTrue(self.named.identity_visible_to(self.hod))
        self.assertEqual(self.named.complainant_display(self.hod), "Abdul Wahab")

    def test_display_without_viewer_masks_anonymous(self):
        self.assertNotIn("Abdul", self.anon.complainant_display(None))
        self.assertEqual(self.named.complainant_display(None), "Abdul Wahab")

    def test_remark_author_is_masked_when_author_is_anonymous_complainant(self):
        remark = ComplaintRemark.objects.create(
            complaint=self.anon, author=self.student, text="Any progress on this?"
        )
        self.assertNotIn("Abdul", remark.author_display(self.anon, self.hod))
        self.assertNotIn("Abdul", remark.author_display(self.anon, self.admin))
        # ...but the complainant themselves still sees their own name.
        self.assertIn("Abdul", remark.author_display(self.anon, self.student))

    def test_status_history_actor_is_masked_for_anonymous_complainant(self):
        self.anon.transition_to(ComplaintStatus.CANCELLED, actor=self.student)
        history = self.anon.status_history.last()
        self.assertNotIn("Abdul", history.actor_display(self.anon, self.hod))

    def test_timeline_never_leaks_identity_to_hod(self):
        ComplaintRemark.objects.create(
            complaint=self.anon, author=self.student, text="Following up."
        )
        rendered = " ".join(
            f"{event['author']} {event['title']} {event['body']}"
            for event in self.anon.timeline(self.hod)
        )
        self.assertNotIn("Abdul", rendered)
        self.assertNotIn("BSIT-084600", rendered)


class QuerysetScopingTests(TestCase):
    def setUp(self):
        self.it = make_department()
        self.hostel = make_department(name="Hostel", code="HSA")
        self.it_student = make_student(email="it.student@test.local", department=self.it)
        self.hostel_student = make_student(
            email="hostel.student@test.local", department=self.hostel
        )
        self.it_hod = make_hod(email="it.hod@test.local", department=self.it)
        self.admin = make_admin()

        self.it_complaint = make_complaint(
            student=self.it_student, department=self.it
        )
        self.hostel_complaint = make_complaint(
            student=self.hostel_student,
            department=self.hostel,
            subject="No hot water in block B",
        )

    def test_student_sees_only_own_complaints(self):
        visible = Complaint.objects.visible_to(self.it_student)
        self.assertEqual(list(visible), [self.it_complaint])

    def test_hod_sees_only_own_department(self):
        visible = Complaint.objects.visible_to(self.it_hod)
        self.assertEqual(list(visible), [self.it_complaint])
        self.assertNotIn(self.hostel_complaint, visible)

    def test_admin_sees_everything(self):
        visible = Complaint.objects.visible_to(self.admin)
        self.assertEqual(visible.count(), 2)

    def test_hod_without_department_sees_nothing(self):
        orphan = make_hod(email="orphan.hod@test.local", department=self.hostel)
        Complaint.objects.filter(pk=self.hostel_complaint.pk).delete()
        orphan.department = None
        orphan.save(update_fields=["department"])
        self.assertEqual(Complaint.objects.visible_to(orphan).count(), 0)

    def test_anonymous_visitor_sees_nothing(self):
        from django.contrib.auth.models import AnonymousUser

        self.assertEqual(Complaint.objects.visible_to(AnonymousUser()).count(), 0)

    def test_can_be_managed_by_respects_department(self):
        hostel_hod = make_hod(email="hostel.hod@test.local", department=self.hostel)
        self.assertTrue(self.it_complaint.can_be_managed_by(self.it_hod))
        self.assertFalse(self.it_complaint.can_be_managed_by(hostel_hod))
        self.assertTrue(self.it_complaint.can_be_managed_by(self.admin))
        self.assertFalse(self.it_complaint.can_be_managed_by(self.it_student))


class AuditLogTests(TestCase):
    def test_record_creates_entry_with_actor_snapshot(self):
        user = make_admin()
        entry = AuditLog.record(
            actor=user, action=AuditAction.UNMASK, target="CMP-1", detail="test"
        )
        self.assertEqual(entry.actor, user)
        self.assertIn(user.get_full_name(), entry.actor_label)
        self.assertIn("CMP-1", str(entry))

    def test_record_without_actor_is_labelled_anonymous(self):
        entry = AuditLog.record(action=AuditAction.LOGIN_FAILED, target="nobody@x.y")
        self.assertEqual(entry.actor_label, "anonymous")
        self.assertIsNone(entry.actor)


class AttachmentPathTests(TestCase):
    def setUp(self):
        self.department = make_department()
        self.student = make_student(department=self.department)
        self.complaint = make_complaint(
            student=self.student, department=self.department
        )

    def _path(self, filename):
        class Stub:
            complaint = self.complaint

        return attachment_upload_path(Stub(), filename)

    def test_path_is_scoped_to_the_complaint(self):
        self.assertTrue(
            self._path("proof.pdf").startswith(f"attachments/{self.complaint.pk}/")
        )

    def test_directory_traversal_is_neutralised(self):
        path = self._path("../../../etc/passwd.png")
        self.assertNotIn("..", path)
        self.assertTrue(path.endswith(".png"))

    def test_hostile_characters_are_stripped(self):
        path = self._path("we;ird name$(rm -rf).jpg")
        stored = path.rsplit("/", 1)[1]
        self.assertNotIn(";", stored)
        self.assertNotIn("$", stored)
        self.assertNotIn(" ", stored)

    def test_filenames_are_unique_per_upload(self):
        self.assertNotEqual(self._path("proof.pdf"), self._path("proof.pdf"))


class DriveToStatusHelperTests(TestCase):
    """Guard the test helper itself so failures point at the code, not the fixture."""

    def test_helper_reaches_every_status(self):
        department = make_department()
        student = make_student(department=department)
        for status in ComplaintStatus.values:
            complaint = make_complaint(
                student=student,
                department=department,
                subject=f"Reaching status {status} in the workflow",
            )
            drive_to_status(complaint, status, actor=student)
            self.assertEqual(complaint.status, status)
