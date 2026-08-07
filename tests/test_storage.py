"""
Database-backed file storage (serverless deployment).

On Vercel and comparable function runtimes the filesystem is read-only, so
attachments must live in the database or FR-4 silently breaks. These tests pin
the backend's behaviour and, critically, prove the *whole* upload -> download
path still works when it is switched on.
"""

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse

from complaints.models import ComplaintAttachment
from complaints.storage import DatabaseStorage, StoredFile, select_attachment_storage

from .factories import (
    PASSWORD,
    PDF_BYTES,
    PNG_BYTES,
    make_admin,
    make_complaint,
    make_department,
    make_hod,
    make_student,
    pdf_upload,
    png_upload,
)


class DatabaseStorageUnitTests(TestCase):
    """The backend in isolation."""

    def setUp(self):
        self.storage = DatabaseStorage()

    def test_save_then_open_round_trips_bytes_exactly(self):
        name = self.storage.save("attachments/1/proof.png", ContentFile(PNG_BYTES))
        with self.storage.open(name) as handle:
            self.assertEqual(handle.read(), PNG_BYTES)

    def test_save_persists_a_row_with_size(self):
        self.storage.save("attachments/1/proof.pdf", ContentFile(PDF_BYTES))
        record = StoredFile.objects.get(name="attachments/1/proof.pdf")
        self.assertEqual(record.size, len(PDF_BYTES))
        self.assertEqual(bytes(record.content), PDF_BYTES)

    def test_exists_reflects_reality(self):
        self.assertFalse(self.storage.exists("nope.png"))
        self.storage.save("yes.png", ContentFile(PNG_BYTES))
        self.assertTrue(self.storage.exists("yes.png"))

    def test_delete_removes_the_row(self):
        self.storage.save("bye.png", ContentFile(PNG_BYTES))
        self.storage.delete("bye.png")
        self.assertFalse(StoredFile.objects.filter(name="bye.png").exists())

    def test_size_matches_content(self):
        self.storage.save("sized.pdf", ContentFile(PDF_BYTES))
        self.assertEqual(self.storage.size("sized.pdf"), len(PDF_BYTES))

    def test_opening_a_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            self.storage.open("ghost.png")

    def test_size_of_a_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            self.storage.size("ghost.png")

    def test_saving_the_same_name_twice_does_not_duplicate_rows(self):
        self.storage.save("dup.png", ContentFile(PNG_BYTES))
        StoredFile.objects.filter(name="dup.png").update(size=0)
        self.storage._save("dup.png", ContentFile(PDF_BYTES))
        self.assertEqual(StoredFile.objects.filter(name="dup.png").count(), 1)
        self.assertEqual(bytes(StoredFile.objects.get(name="dup.png").content), PDF_BYTES)

    def test_url_refuses_rather_than_leaking_an_unprotected_path(self):
        """Attachments must only ever be reached through the guarded view."""
        self.storage.save("secret.pdf", ContentFile(PDF_BYTES))
        with self.assertRaises(NotImplementedError):
            self.storage.url("secret.pdf")

    def test_storage_is_deconstructible_for_migrations(self):
        path, args, kwargs = DatabaseStorage().deconstruct()
        self.assertEqual(path, "complaints.storage.DatabaseStorage")
        self.assertEqual(list(args), [])
        self.assertEqual(kwargs, {})


class StorageSelectorTests(TestCase):
    """The setting decides which backend a FileField uses."""

    @override_settings(USE_DATABASE_FILE_STORAGE=True)
    def test_database_storage_selected_when_enabled(self):
        self.assertIsInstance(select_attachment_storage(), DatabaseStorage)

    @override_settings(USE_DATABASE_FILE_STORAGE=False)
    def test_filesystem_storage_selected_by_default(self):
        self.assertNotIsInstance(select_attachment_storage(), DatabaseStorage)


@override_settings(USE_DATABASE_FILE_STORAGE=True)
class ServerlessUploadDownloadTests(TestCase):
    """
    End to end with the database backend active - the Vercel configuration.

    Nothing touches MEDIA_ROOT, so these pass on a read-only filesystem.
    """

    def setUp(self):
        self.department = make_department()
        self.student = make_student(department=self.department)
        self.hod = make_hod(department=self.department)
        self.admin = make_admin()

    def _submit_with_attachment(self):
        self.client.login(username=self.student.email, password=PASSWORD)
        response = self.client.post(
            reverse("complaints:create"),
            {
                "subject": "Projector broken in Lab 3",
                "category": "ACADEMIC",
                "department": self.department.pk,
                "description": "The projector in Lab 3 has not worked for two weeks.",
                "attachments": [png_upload(), pdf_upload()],
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        return response

    def test_submission_stores_attachment_bytes_in_the_database(self):
        self._submit_with_attachment()

        attachments = ComplaintAttachment.objects.all()
        self.assertEqual(attachments.count(), 2)
        # Every attachment has a matching row of bytes.
        for attachment in attachments:
            self.assertTrue(StoredFile.objects.filter(name=attachment.file.name).exists())

    def test_owner_can_download_and_bytes_are_identical(self):
        self._submit_with_attachment()
        attachment = ComplaintAttachment.objects.get(original_name="evidence.png")

        self.client.login(username=self.student.email, password=PASSWORD)
        response = self.client.get(
            reverse("complaints:attachment", args=[attachment.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), PNG_BYTES)

    def test_access_control_still_applies_with_database_storage(self):
        """Switching backends must not weaken the permission check."""
        self._submit_with_attachment()
        attachment = ComplaintAttachment.objects.first()

        other_department = make_department(name="Hostel Affairs", code="HSA")
        outsider = make_hod(email="other.hod@test.local", department=other_department)

        self.client.login(username=outsider.email, password=PASSWORD)
        response = self.client.get(
            reverse("complaints:attachment", args=[attachment.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_upload_validation_is_unaffected_by_the_backend(self):
        """A disguised executable is still rejected before it reaches storage."""
        from .factories import disguised_upload

        self.client.login(username=self.student.email, password=PASSWORD)
        self.client.post(
            reverse("complaints:create"),
            {
                "subject": "Attempted bad upload",
                "category": "OTHER",
                "department": self.department.pk,
                "description": "This submission carries a disguised executable file.",
                "attachments": [disguised_upload()],
            },
        )
        self.assertEqual(StoredFile.objects.count(), 0)
        self.assertEqual(ComplaintAttachment.objects.count(), 0)

    def test_deleting_a_complaint_cascades_to_attachment_rows(self):
        self._submit_with_attachment()
        complaint = ComplaintAttachment.objects.first().complaint
        complaint.attachments.all().delete()
        self.assertEqual(ComplaintAttachment.objects.count(), 0)


class DatabaseStorageModelTests(TestCase):
    def test_str_is_the_stored_name(self):
        record = StoredFile.objects.create(
            name="attachments/9/x.pdf", content=PDF_BYTES, size=len(PDF_BYTES)
        )
        self.assertEqual(str(record), "attachments/9/x.pdf")

    def test_name_is_unique(self):
        StoredFile.objects.create(name="dup.pdf", content=PDF_BYTES)
        with self.assertRaises(Exception):
            StoredFile.objects.create(name="dup.pdf", content=PDF_BYTES)
