"""Shared fixtures for the test suite (plain helpers - no extra dependency)."""

from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile

from accounts.models import Department, Role, User
from complaints.models import Complaint, ComplaintCategory, ComplaintStatus

PASSWORD = "TestPass!2026"

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)
PDF_BYTES = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"


def make_department(name="Information Technology", code="IT"):
    return Department.objects.create(name=name, code=code)


def make_user(
    *,
    email,
    role=Role.STUDENT,
    department=None,
    full_name=None,
    identifier=None,
    password=PASSWORD,
    is_active=True,
):
    user = User(
        email=email,
        username=email,
        full_name=full_name or email.split("@")[0].replace(".", " ").title(),
        identifier=identifier,
        role=role,
        department=department,
        is_active=is_active,
    )
    user.set_password(password)
    user.save()
    return user


def make_student(email="student@test.local", department=None, **kwargs):
    return make_user(email=email, role=Role.STUDENT, department=department, **kwargs)


def make_hod(email="hod@test.local", department=None, **kwargs):
    return make_user(email=email, role=Role.HOD, department=department, **kwargs)


def make_admin(email="admin@test.local", **kwargs):
    return make_user(email=email, role=Role.ADMIN, department=None, **kwargs)


def make_complaint(
    *,
    student,
    department,
    subject="Projector in room 14 is broken",
    description="The projector has been out of order for two weeks and lectures suffer.",
    category=ComplaintCategory.ACADEMIC,
    is_anonymous=False,
    status=ComplaintStatus.SUBMITTED,
):
    complaint = Complaint.objects.create(
        subject=subject,
        description=description,
        category=category,
        department=department,
        student=student,
        is_anonymous=is_anonymous,
    )
    if status != ComplaintStatus.SUBMITTED:
        drive_to_status(complaint, status, actor=student)
    return complaint


#: Ordered transition chains used to place a complaint into a target status.
PATHS = {
    ComplaintStatus.SUBMITTED: [],
    ComplaintStatus.CANCELLED: [ComplaintStatus.CANCELLED],
    ComplaintStatus.ASSIGNED: [ComplaintStatus.ASSIGNED],
    ComplaintStatus.IN_PROGRESS: [
        ComplaintStatus.ASSIGNED,
        ComplaintStatus.IN_PROGRESS,
    ],
    ComplaintStatus.RESOLVED: [
        ComplaintStatus.ASSIGNED,
        ComplaintStatus.IN_PROGRESS,
        ComplaintStatus.RESOLVED,
    ],
    ComplaintStatus.CLOSED: [
        ComplaintStatus.ASSIGNED,
        ComplaintStatus.IN_PROGRESS,
        ComplaintStatus.RESOLVED,
        ComplaintStatus.CLOSED,
    ],
}


def drive_to_status(complaint, target, actor=None):
    for status in PATHS[target]:
        complaint.transition_to(status, actor=actor)
    return complaint


def png_upload(name="evidence.png"):
    return SimpleUploadedFile(name, PNG_BYTES, content_type="image/png")


def pdf_upload(name="evidence.pdf"):
    return SimpleUploadedFile(name, PDF_BYTES, content_type="application/pdf")


def oversized_upload(name="huge.png", megabytes=6):
    payload = PNG_BYTES + b"\x00" * (megabytes * 1024 * 1024)
    return SimpleUploadedFile(name, payload, content_type="image/png")


def executable_upload(name="payload.exe"):
    return SimpleUploadedFile(
        name, b"MZ\x90\x00\x03", content_type="application/octet-stream"
    )


def disguised_upload(name="payload.pdf"):
    """An executable renamed with an allowed extension - must still be rejected."""
    return SimpleUploadedFile(name, b"MZ\x90\x00\x03", content_type="application/pdf")


def read_bytes(file_field):
    buffer = BytesIO()
    for chunk in file_field.chunks():
        buffer.write(chunk)
    return buffer.getvalue()
