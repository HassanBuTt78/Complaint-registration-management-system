"""Dashboard, analytics, report and export tests (FR-6, FR-7, FR-11)."""

import csv
import io

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import AuditAction, AuditLog
from complaints.models import Complaint, ComplaintCategory, ComplaintStatus

from .factories import (
    make_admin,
    make_complaint,
    make_department,
    make_hod,
    make_student,
)


class DashboardDataTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.it = make_department()
        cls.hostel = make_department(name="Hostel & Student Affairs", code="HSA")

        cls.student = make_student(email="dash.student@test.local", department=cls.it)
        cls.it_hod = make_hod(email="dash.hod@test.local", department=cls.it)
        cls.admin = make_admin(email="dash.admin@test.local")

        cls.submitted = make_complaint(
            student=cls.student,
            department=cls.it,
            subject="Submitted complaint about the timetable",
            description="The timetable clashes with the laboratory sessions weekly.",
        )
        cls.in_progress = make_complaint(
            student=cls.student,
            department=cls.it,
            subject="In progress complaint about grading",
            description="The grading of the mid-term paper appears to be incorrect.",
            category=ComplaintCategory.ACADEMIC,
            status=ComplaintStatus.IN_PROGRESS,
        )
        cls.closed = make_complaint(
            student=cls.student,
            department=cls.it,
            subject="Closed complaint about lab access",
            description="Access to the laboratory outside class hours was refused.",
            status=ComplaintStatus.CLOSED,
        )
        cls.hostel_complaint = make_complaint(
            student=cls.student,
            department=cls.hostel,
            subject="Hostel complaint about water",
            description="Water supply in the residence block is highly irregular.",
            category=ComplaintCategory.HOSTEL,
        )


class StudentDashboardTests(DashboardDataTestCase):
    def setUp(self):
        self.client.force_login(self.student)
        self.url = reverse("dashboards:student")

    def test_dashboard_lists_all_of_the_students_complaints(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        for complaint in (self.submitted, self.in_progress, self.closed):
            self.assertContains(response, complaint.reference)

    def test_counters_are_correct(self):
        response = self.client.get(self.url)
        self.assertEqual(response.context["total"], 4)
        self.assertEqual(response.context["open_count"], 3)  # excludes CLOSED
        self.assertEqual(response.context["resolved_count"], 1)

    def test_status_filter_narrows_the_list(self):
        response = self.client.get(self.url, {"status": ComplaintStatus.CLOSED})
        self.assertContains(response, self.closed.reference)
        self.assertNotContains(response, self.submitted.reference)

    def test_keyword_search_narrows_the_list(self):
        response = self.client.get(self.url, {"q": "grading"})
        self.assertContains(response, self.in_progress.reference)
        self.assertNotContains(response, self.submitted.reference)

    def test_invalid_date_range_is_reported(self):
        today = timezone.localdate()
        response = self.client.get(
            self.url,
            {
                "date_from": today.isoformat(),
                "date_to": (today - timezone.timedelta(days=5)).isoformat(),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "must not precede")

    def test_dashboard_shows_an_empty_state(self):
        Complaint.objects.all().delete()
        response = self.client.get(self.url)
        self.assertContains(response, "not submitted any complaints yet")

    def test_pagination_works(self):
        for index in range(20):
            make_complaint(
                student=self.student,
                department=self.it,
                subject=f"Bulk complaint number {index} for pagination",
                description="A sufficiently long description for validation purposes.",
            )
        response = self.client.get(self.url, {"page": 2})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].number, 2)


class HODDashboardTests(DashboardDataTestCase):
    def setUp(self):
        self.client.force_login(self.it_hod)
        self.url = reverse("dashboards:hod")

    def test_dashboard_is_scoped_to_the_department(self):
        response = self.client.get(self.url)
        self.assertEqual(response.context["total"], 3)
        self.assertNotContains(response, self.hostel_complaint.reference)

    def test_unassigned_counter(self):
        response = self.client.get(self.url)
        self.assertEqual(response.context["unassigned"], 3)

    def test_department_name_is_shown(self):
        self.assertContains(self.client.get(self.url), "Information Technology")

    def test_hod_without_a_department_is_denied(self):
        self.it_hod.department = None
        self.it_hod.save(update_fields=["department"])
        self.assertEqual(self.client.get(self.url).status_code, 403)


class AdminDashboardTests(DashboardDataTestCase):
    def setUp(self):
        self.client.force_login(self.admin)
        self.url = reverse("dashboards:admin")

    def test_dashboard_shows_every_department(self):
        response = self.client.get(self.url)
        self.assertEqual(response.context["total"], 4)
        self.assertContains(response, self.hostel_complaint.reference)

    def test_department_filter_is_available_to_the_admin(self):
        response = self.client.get(self.url, {"department": self.hostel.pk})
        self.assertContains(response, self.hostel_complaint.reference)
        self.assertNotContains(response, self.submitted.reference)

    def test_summary_counters(self):
        response = self.client.get(self.url)
        self.assertEqual(response.context["department_count"], 2)
        self.assertGreaterEqual(response.context["user_count"], 3)


class AnalyticsTests(DashboardDataTestCase):
    def test_admin_analytics_covers_all_departments(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("dashboards:analytics"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total"], 4)
        self.assertEqual(response.context["scope"], "All departments")

    def test_hod_analytics_is_department_scoped(self):
        self.client.force_login(self.it_hod)
        response = self.client.get(reverse("dashboards:analytics"))
        self.assertEqual(response.context["total"], 3)
        self.assertEqual(response.context["scope"], "Information Technology")

    def test_per_status_breakdown_covers_every_status(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("dashboards:analytics"))
        self.assertEqual(len(response.context["per_status"]), 6)

    def test_per_category_breakdown_covers_every_category(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("dashboards:analytics"))
        self.assertEqual(len(response.context["per_category"]), 4)

    def test_resolution_rate_and_average_are_computed(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("dashboards:analytics"))
        self.assertEqual(response.context["resolved_total"], 1)
        self.assertEqual(response.context["resolution_rate"], 25.0)
        self.assertGreaterEqual(response.context["avg_resolution_hours"], 0)

    def test_monthly_trend_is_present(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("dashboards:analytics"))
        trend = response.context["monthly_trend"]
        self.assertTrue(trend)
        self.assertEqual(sum(row["total"] for row in trend), 4)

    def test_analytics_survives_an_empty_dataset(self):
        Complaint.objects.all().delete()
        self.client.force_login(self.admin)
        response = self.client.get(reverse("dashboards:analytics"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total"], 0)
        self.assertEqual(response.context["resolution_rate"], 0.0)

    def test_chart_datasets_are_serialised_into_the_page(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("dashboards:analytics"))
        self.assertContains(response, 'id="chart-department-data"')
        self.assertContains(response, 'id="chart-status-data"')
        self.assertContains(response, 'id="chart-category-data"')
        self.assertContains(response, 'id="chart-monthly-data"')

    def test_student_cannot_view_analytics(self):
        self.client.force_login(self.student)
        self.assertEqual(
            self.client.get(reverse("dashboards:analytics")).status_code, 403
        )


class ReportExportTests(DashboardDataTestCase):
    def setUp(self):
        self.url = reverse("dashboards:reports")

    def test_report_page_renders_with_a_summary(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["summary"]["total"], 4)

    def test_csv_export_has_the_right_headers_and_rows(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.url, {"export": "csv"})

        self.assertIn("text/csv", response["Content-Type"])
        self.assertIn("attachment;", response["Content-Disposition"])
        self.assertIn(".csv", response["Content-Disposition"])

        rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
        self.assertEqual(len(rows), 4)
        self.assertIn("Reference", rows[0])
        self.assertIn("Complainant", rows[0])

    def test_csv_export_respects_the_active_filters(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            self.url, {"export": "csv", "status": ComplaintStatus.CLOSED}
        )
        rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Reference"], self.closed.reference)

    def test_pdf_export_returns_a_valid_pdf(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.url, {"export": "pdf"})
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertIn(".pdf", response["Content-Disposition"])

    def test_export_is_audited(self):
        AuditLog.objects.all().delete()
        self.client.force_login(self.admin)
        self.client.get(self.url, {"export": "csv"})
        entry = AuditLog.objects.filter(action=AuditAction.REPORT_EXPORTED).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.target, "CSV")

    def test_empty_export_warns_instead_of_producing_a_blank_file(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            self.url, {"export": "csv", "q": "no-such-complaint-anywhere"}, follow=True
        )
        self.assertContains(response, "nothing to export")

    def test_unknown_export_format_renders_the_page(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.url, {"export": "docx"})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboards/reports.html")

    def test_student_cannot_export(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(self.url, {"export": "csv"}).status_code, 403)


class ErrorPageTests(TestCase):
    def test_404_page_is_branded(self):
        department = make_department()
        self.client.force_login(make_student(department=department))
        response = self.client.get("/no/such/page/")
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "errors/404.html")

    def test_403_page_is_branded(self):
        department = make_department()
        self.client.force_login(make_student(department=department))
        response = self.client.get(reverse("dashboards:admin"))
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, "errors/403.html")


class SeedCommandTests(TestCase):
    """The demo dataset must load cleanly into an empty database."""

    def test_seed_command_creates_the_documented_dataset(self):
        from io import StringIO

        from django.core.management import call_command

        from accounts.models import Department, Role, User

        call_command("seed_demo_data", stdout=StringIO())

        self.assertEqual(Department.objects.count(), 3)
        self.assertEqual(User.objects.filter(role=Role.ADMIN).count(), 1)
        self.assertEqual(User.objects.filter(role=Role.HOD).count(), 2)
        self.assertEqual(User.objects.filter(role=Role.STUDENT).count(), 5)
        self.assertEqual(Complaint.objects.count(), 15)

    def test_seeded_complaints_cover_every_status(self):
        from io import StringIO

        from django.core.management import call_command

        call_command("seed_demo_data", stdout=StringIO())
        statuses = set(Complaint.objects.values_list("status", flat=True))
        self.assertEqual(statuses, set(ComplaintStatus.values))

    def test_seed_includes_anonymous_complaints(self):
        from io import StringIO

        from django.core.management import call_command

        call_command("seed_demo_data", stdout=StringIO())
        self.assertGreater(Complaint.objects.filter(is_anonymous=True).count(), 0)

    def test_seed_command_is_idempotent(self):
        from io import StringIO

        from django.core.management import call_command

        call_command("seed_demo_data", stdout=StringIO())
        call_command("seed_demo_data", stdout=StringIO())

        from accounts.models import User

        self.assertEqual(Complaint.objects.count(), 15)
        self.assertEqual(User.objects.count(), 8)

    def test_seeded_accounts_can_sign_in(self):
        from io import StringIO

        from django.core.management import call_command

        call_command("seed_demo_data", stdout=StringIO())
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "principal@mao.edu.pk", "password": "Portal@2026"},
        )
        self.assertEqual(response.status_code, 302)
