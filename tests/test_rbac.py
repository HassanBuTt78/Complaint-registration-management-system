"""
Role-Based Access Control and anonymity, end to end (FR-5, FR-7, FR-12).

These are the security-critical tests: they prove that no view, filter, search,
report or export can be used by an HOD to reach another department's data or an
anonymous complainant's identity.
"""

import csv
import io

from django.test import TestCase
from django.urls import reverse

from accounts.models import AuditAction, AuditLog, Role
from complaints.models import Complaint, ComplaintRemark, ComplaintStatus

from .factories import (
    make_admin,
    make_complaint,
    make_department,
    make_hod,
    make_student,
)

SECRET_NAME = "Zulfiqar Anonymous"
SECRET_ID = "ANON-ROLL-777"
SECRET_EMAIL = "zulfiqar.secret@test.local"


class RBACBaseTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.it = make_department()
        cls.hostel = make_department(name="Hostel & Student Affairs", code="HSA")

        cls.student = make_student(
            email=SECRET_EMAIL,
            department=cls.it,
            full_name=SECRET_NAME,
            identifier=SECRET_ID,
        )
        cls.other_student = make_student(
            email="visible.student@test.local",
            department=cls.it,
            full_name="Visible Student",
            identifier="VIS-001",
        )
        cls.it_hod = make_hod(email="it.hod@test.local", department=cls.it)
        cls.hostel_hod = make_hod(email="hostel.hod@test.local", department=cls.hostel)
        cls.admin = make_admin(email="principal@test.local")

        cls.anonymous_complaint = make_complaint(
            student=cls.student,
            department=cls.it,
            subject="Anonymous report about unfair grading",
            is_anonymous=True,
        )
        cls.named_complaint = make_complaint(
            student=cls.other_student,
            department=cls.it,
            subject="Named complaint about the lab timetable",
            description="The timetable for laboratory sessions clashes with lectures.",
        )
        cls.hostel_complaint = make_complaint(
            student=cls.other_student,
            department=cls.hostel,
            subject="Hostel water supply is intermittent",
            description="Water is only available for two hours each morning.",
        )


class RoleRoutingTests(RBACBaseTestCase):
    """Each role lands on - and is confined to - its own dashboard."""

    def test_student_is_routed_to_the_student_dashboard(self):
        self.client.force_login(self.student)
        self.assertRedirects(
            self.client.get(reverse("dashboards:home")), reverse("dashboards:student")
        )

    def test_hod_is_routed_to_the_hod_dashboard(self):
        self.client.force_login(self.it_hod)
        self.assertRedirects(
            self.client.get(reverse("dashboards:home")), reverse("dashboards:hod")
        )

    def test_admin_is_routed_to_the_admin_dashboard(self):
        self.client.force_login(self.admin)
        self.assertRedirects(
            self.client.get(reverse("dashboards:home")), reverse("dashboards:admin")
        )

    def test_unauthenticated_visitor_is_sent_to_login(self):
        self.assertRedirects(
            self.client.get(reverse("dashboards:home")), reverse("accounts:login")
        )


class ForbiddenUrlMatrixTests(RBACBaseTestCase):
    """Every restricted URL, checked against every role that must not reach it."""

    STUDENT_FORBIDDEN = [
        "dashboards:hod",
        "dashboards:admin",
        "dashboards:analytics",
        "dashboards:reports",
        "dashboards:user_list",
        "dashboards:user_create",
        "dashboards:departments",
        "dashboards:activity",
    ]
    HOD_FORBIDDEN = [
        "dashboards:student",
        "dashboards:admin",
        "dashboards:user_list",
        "dashboards:user_create",
        "dashboards:departments",
        "dashboards:activity",
    ]
    ADMIN_FORBIDDEN = ["dashboards:student", "dashboards:hod"]

    def _assert_forbidden(self, user, names):
        self.client.force_login(user)
        for name in names:
            with self.subTest(user=user.role, url=name):
                response = self.client.get(reverse(name))
                self.assertEqual(
                    response.status_code,
                    403,
                    f"{user.role} unexpectedly reached {name}",
                )

    def test_student_cannot_reach_staff_urls(self):
        self._assert_forbidden(self.student, self.STUDENT_FORBIDDEN)

    def test_hod_cannot_reach_admin_or_student_urls(self):
        self._assert_forbidden(self.it_hod, self.HOD_FORBIDDEN)

    def test_admin_cannot_reach_role_specific_dashboards(self):
        self._assert_forbidden(self.admin, self.ADMIN_FORBIDDEN)

    def test_student_cannot_reach_the_unmask_view(self):
        self.client.force_login(self.student)
        response = self.client.get(
            reverse("dashboards:unmask", args=[self.anonymous_complaint.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_hod_cannot_reach_the_unmask_view(self):
        self.client.force_login(self.it_hod)
        response = self.client.get(
            reverse("dashboards:unmask", args=[self.anonymous_complaint.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_blocked_access_is_written_to_the_audit_log(self):
        AuditLog.objects.all().delete()
        self.client.force_login(self.student)
        self.client.get(reverse("dashboards:admin"))
        entry = AuditLog.objects.filter(action=AuditAction.ACCESS_DENIED).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.actor, self.student)
        self.assertIn("/dashboard/admin/", entry.target)


class DepartmentIsolationTests(RBACBaseTestCase):
    """FR-7: an HOD must never reach another department's complaints."""

    def test_hod_dashboard_lists_only_own_department(self):
        self.client.force_login(self.it_hod)
        response = self.client.get(reverse("dashboards:hod"))
        self.assertContains(response, self.named_complaint.reference)
        self.assertNotContains(response, self.hostel_complaint.reference)

    def test_hod_cannot_open_a_foreign_complaint(self):
        self.client.force_login(self.it_hod)
        response = self.client.get(self.hostel_complaint.get_absolute_url())
        self.assertEqual(response.status_code, 403)

    def test_foreign_complaint_access_is_audited(self):
        AuditLog.objects.all().delete()
        self.client.force_login(self.it_hod)
        self.client.get(self.hostel_complaint.get_absolute_url())
        self.assertTrue(
            AuditLog.objects.filter(action=AuditAction.ACCESS_DENIED).exists()
        )

    def test_hod_cannot_widen_scope_via_the_department_query_parameter(self):
        """The department filter field does not exist for an HOD - it is ignored."""
        self.client.force_login(self.it_hod)
        response = self.client.get(
            reverse("dashboards:hod"), {"department": self.hostel.pk}
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.hostel_complaint.reference)

    def test_hod_search_cannot_surface_foreign_complaints(self):
        self.client.force_login(self.it_hod)
        response = self.client.get(reverse("dashboards:hod"), {"q": "water supply"})
        self.assertNotContains(response, self.hostel_complaint.reference)

    def test_hod_report_export_is_department_scoped(self):
        self.client.force_login(self.it_hod)
        response = self.client.get(reverse("dashboards:reports"), {"export": "csv"})
        body = response.content.decode("utf-8-sig")
        self.assertIn(self.named_complaint.reference, body)
        self.assertNotIn(self.hostel_complaint.reference, body)

    def test_student_cannot_open_another_students_complaint(self):
        self.client.force_login(self.student)
        response = self.client.get(self.named_complaint.get_absolute_url())
        self.assertEqual(response.status_code, 403)

    def test_nonexistent_complaint_returns_404(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get("/complaints/999999/").status_code, 404)


class AnonymityEnforcementTests(RBACBaseTestCase):
    """
    FR-5: the complainant's identity must be unreachable to an HOD through *any*
    surface - detail view, list view, search, filter, report or export.
    """

    def _assert_no_leak(self, response):
        body = response.content.decode(response.charset or "utf-8", errors="ignore")
        self.assertNotIn(SECRET_NAME, body)
        self.assertNotIn(SECRET_ID, body)
        self.assertNotIn(SECRET_EMAIL, body)

    def test_detail_view_masks_identity_from_hod(self):
        self.client.force_login(self.it_hod)
        response = self.client.get(self.anonymous_complaint.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Anonymous")
        self._assert_no_leak(response)

    def test_dashboard_list_masks_identity_from_hod(self):
        self.client.force_login(self.it_hod)
        self._assert_no_leak(self.client.get(reverse("dashboards:hod")))

    def test_reports_page_masks_identity_from_hod(self):
        self.client.force_login(self.it_hod)
        self._assert_no_leak(self.client.get(reverse("dashboards:reports")))

    def test_csv_export_masks_identity_from_hod(self):
        self.client.force_login(self.it_hod)
        response = self.client.get(reverse("dashboards:reports"), {"export": "csv"})
        body = response.content.decode("utf-8-sig")
        self.assertIn(self.anonymous_complaint.reference, body)
        self.assertNotIn(SECRET_NAME, body)
        self.assertNotIn(SECRET_ID, body)

        rows = list(csv.DictReader(io.StringIO(body)))
        anon_row = next(
            row
            for row in rows
            if row["Reference"] == self.anonymous_complaint.reference
        )
        self.assertIn("Anonymous", anon_row["Complainant"])

    def test_pdf_export_masks_identity_from_hod(self):
        self.client.force_login(self.it_hod)
        response = self.client.get(reverse("dashboards:reports"), {"export": "pdf"})
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertNotIn(SECRET_NAME.encode(), response.content)
        self.assertNotIn(SECRET_ID.encode(), response.content)

    def test_analytics_page_never_names_complainants(self):
        self.client.force_login(self.it_hod)
        self._assert_no_leak(self.client.get(reverse("dashboards:analytics")))

    def test_hod_cannot_find_the_complaint_by_searching_the_students_name(self):
        self.client.force_login(self.it_hod)
        for probe in (SECRET_NAME, SECRET_ID, SECRET_EMAIL, "Zulfiqar"):
            with self.subTest(probe=probe):
                response = self.client.get(reverse("dashboards:hod"), {"q": probe})
                self.assertNotContains(
                    response, self.anonymous_complaint.reference
                )

    def test_hod_sees_the_students_remark_without_the_name(self):
        ComplaintRemark.objects.create(
            complaint=self.anonymous_complaint,
            author=self.student,
            text="Has there been any progress on this matter?",
        )
        self.client.force_login(self.it_hod)
        response = self.client.get(self.anonymous_complaint.get_absolute_url())
        self.assertContains(response, "any progress on this matter")
        self._assert_no_leak(response)

    def test_status_change_by_the_student_does_not_leak_the_name(self):
        self.anonymous_complaint.transition_to(
            ComplaintStatus.CANCELLED, actor=self.student
        )
        self.client.force_login(self.it_hod)
        self._assert_no_leak(
            self.client.get(self.anonymous_complaint.get_absolute_url())
        )

    def test_named_complaint_identity_is_visible_to_the_hod(self):
        self.client.force_login(self.it_hod)
        response = self.client.get(self.named_complaint.get_absolute_url())
        self.assertContains(response, "Visible Student")

    def test_student_still_sees_their_own_identity(self):
        self.client.force_login(self.student)
        response = self.client.get(self.anonymous_complaint.get_absolute_url())
        self.assertContains(response, SECRET_NAME)

    def test_admin_detail_view_offers_the_unmask_action(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.anonymous_complaint.get_absolute_url())
        self.assertContains(response, "Unmask identity")


class UnmaskTests(RBACBaseTestCase):
    """FR-5 / UC18: only the Principal may unmask, and it is always logged."""

    def setUp(self):
        self.url = reverse("dashboards:unmask", args=[self.anonymous_complaint.pk])

    def test_confirmation_page_renders_for_admin(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reveal anonymous complainant")

    def test_confirmation_page_does_not_pre_leak_the_identity(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertNotContains(response, SECRET_NAME)

    def test_unmasking_reveals_the_identity_and_writes_an_audit_entry(self):
        AuditLog.objects.all().delete()
        self.client.force_login(self.admin)
        response = self.client.post(
            self.url, {"reason": "Formal disciplinary investigation 2026/17"}, follow=True
        )
        self.assertContains(response, SECRET_NAME)

        entry = AuditLog.objects.filter(action=AuditAction.UNMASK).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.actor, self.admin)
        self.assertEqual(entry.target, self.anonymous_complaint.reference)
        self.assertIn(SECRET_NAME, entry.detail)
        self.assertIn("2026/17", entry.detail)

    def test_a_reason_is_mandatory(self):
        self.client.force_login(self.admin)
        response = self.client.post(self.url, {"reason": "no"}, follow=True)
        self.assertContains(response, "state a reason")
        self.assertFalse(AuditLog.objects.filter(action=AuditAction.UNMASK).exists())

    def test_unmasking_does_not_change_the_complaint(self):
        self.client.force_login(self.admin)
        self.client.post(self.url, {"reason": "Investigation reference 2026/17"})
        self.anonymous_complaint.refresh_from_db()
        self.assertTrue(self.anonymous_complaint.is_anonymous)

    def test_hod_still_cannot_see_the_identity_after_an_admin_unmasked_it(self):
        self.client.force_login(self.admin)
        self.client.post(self.url, {"reason": "Investigation reference 2026/17"})

        self.client.force_login(self.it_hod)
        response = self.client.get(self.anonymous_complaint.get_absolute_url())
        body = response.content.decode()
        self.assertNotIn(SECRET_NAME, body)
        self.assertNotIn(SECRET_ID, body)

    def test_unmasking_a_named_complaint_is_a_no_op(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("dashboards:unmask", args=[self.named_complaint.pk]), follow=True
        )
        self.assertContains(response, "not submitted anonymously")

    def test_service_refuses_a_non_admin_actor(self):
        from complaints.services import unmask_complaint

        with self.assertRaises(PermissionError):
            unmask_complaint(complaint=self.anonymous_complaint, actor=self.it_hod)


class UserManagementTests(RBACBaseTestCase):
    """FR-10 / UC17: only the Principal manages accounts."""

    def test_admin_can_create_an_hod(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("dashboards:user_create"),
            {
                "full_name": "New HOD",
                "email": "new.hod@test.local",
                "identifier": "STAFF-NEW",
                "phone": "",
                "role": Role.HOD,
                "department": self.hostel.pk,
                "is_active": "on",
                "password1": "Str0ng!Portal2026",
                "password2": "Str0ng!Portal2026",
            },
        )
        self.assertRedirects(response, reverse("dashboards:user_list"))
        from accounts.models import User

        created = User.objects.get(email="new.hod@test.local")
        self.assertEqual(created.role, Role.HOD)
        self.assertEqual(created.department, self.hostel)
        self.assertTrue(
            AuditLog.objects.filter(action=AuditAction.USER_CREATED).exists()
        )

    def test_creating_an_hod_without_a_department_is_blocked(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("dashboards:user_create"),
            {
                "full_name": "Broken HOD",
                "email": "broken.hod@test.local",
                "role": Role.HOD,
                "department": "",
                "is_active": "on",
                "password1": "Str0ng!Portal2026",
                "password2": "Str0ng!Portal2026",
            },
        )
        self.assertEqual(response.status_code, 200)
        from accounts.models import User

        self.assertFalse(User.objects.filter(email="broken.hod@test.local").exists())

    def test_admin_can_deactivate_a_user(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("dashboards:user_toggle", args=[self.other_student.pk])
        )
        self.assertRedirects(response, reverse("dashboards:user_list"))
        self.other_student.refresh_from_db()
        self.assertFalse(self.other_student.is_active)
        self.assertTrue(
            AuditLog.objects.filter(action=AuditAction.USER_DEACTIVATED).exists()
        )

    def test_admin_cannot_deactivate_themselves(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("dashboards:user_toggle", args=[self.admin.pk]))
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_admin_can_edit_a_user(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("dashboards:user_edit", args=[self.other_student.pk]),
            {
                "full_name": "Renamed Student",
                "email": self.other_student.email,
                "identifier": self.other_student.identifier,
                "phone": "",
                "role": Role.STUDENT,
                "department": self.it.pk,
                "is_active": "on",
                "password1": "",
                "password2": "",
            },
        )
        self.assertRedirects(response, reverse("dashboards:user_list"))
        self.other_student.refresh_from_db()
        self.assertEqual(self.other_student.full_name, "Renamed Student")

    def test_hod_cannot_create_users(self):
        self.client.force_login(self.it_hod)
        self.assertEqual(
            self.client.get(reverse("dashboards:user_create")).status_code, 403
        )

    def test_hod_cannot_toggle_a_user(self):
        self.client.force_login(self.it_hod)
        response = self.client.post(
            reverse("dashboards:user_toggle", args=[self.student.pk])
        )
        self.assertEqual(response.status_code, 403)
        self.student.refresh_from_db()
        self.assertTrue(self.student.is_active)

    def test_user_list_search_and_role_filter(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("dashboards:user_list"), {"q": "Visible"})
        self.assertContains(response, "Visible Student")
        response = self.client.get(
            reverse("dashboards:user_list"), {"role": Role.HOD}
        )
        self.assertNotContains(response, "Visible Student")


class DepartmentAdminTests(RBACBaseTestCase):
    def test_admin_can_create_a_department(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("dashboards:departments"),
            {"name": "Examinations", "code": "exm", "description": "", "is_active": "on"},
        )
        self.assertRedirects(response, reverse("dashboards:departments"))
        from accounts.models import Department

        self.assertTrue(Department.objects.filter(code="EXM").exists())

    def test_hod_cannot_manage_departments(self):
        self.client.force_login(self.it_hod)
        self.assertEqual(
            self.client.get(reverse("dashboards:departments")).status_code, 403
        )


class ActivityLogTests(RBACBaseTestCase):
    def test_admin_can_view_the_activity_log(self):
        AuditLog.record(actor=self.admin, action=AuditAction.LOGIN_SUCCESS, target="x")
        self.client.force_login(self.admin)
        response = self.client.get(reverse("dashboards:activity"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "System activity log")

    def test_activity_log_can_be_filtered(self):
        AuditLog.record(actor=self.admin, action=AuditAction.UNMASK, target="CMP-X")
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("dashboards:activity"), {"action": AuditAction.UNMASK, "q": "CMP-X"}
        )
        self.assertContains(response, "CMP-X")

    def test_student_cannot_view_the_activity_log(self):
        self.client.force_login(self.student)
        self.assertEqual(
            self.client.get(reverse("dashboards:activity")).status_code, 403
        )


class DirectObjectReferenceTests(RBACBaseTestCase):
    """Sweep every complaint id against every user - no IDOR anywhere."""

    def test_no_user_can_open_a_complaint_outside_their_scope(self):
        users = [self.student, self.other_student, self.it_hod, self.hostel_hod, self.admin]
        complaints = list(Complaint.objects.all())

        for user in users:
            self.client.force_login(user)
            permitted = set(
                Complaint.objects.visible_to(user).values_list("pk", flat=True)
            )
            for complaint in complaints:
                with self.subTest(user=user.email, complaint=complaint.reference):
                    status = self.client.get(complaint.get_absolute_url()).status_code
                    if complaint.pk in permitted:
                        self.assertEqual(status, 200)
                    else:
                        self.assertIn(status, (403, 404))
