"""
``python manage.py seed_demo_data``

Creates a fully populated demo environment: 3 departments, 1 Principal/Admin,
2 HODs, 5 students and 15 complaints spread across every status (including
anonymous ones), so the portal is presentable immediately after setup.

Idempotent: re-running updates the existing demo accounts instead of
duplicating them. Pass ``--flush-complaints`` to rebuild the complaint set.
"""

import random

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import Department, Role, User
from complaints.models import (
    Complaint,
    ComplaintCategory,
    ComplaintRemark,
    ComplaintStatus,
    ComplaintStatusHistory,
)

DEMO_PASSWORD = "Portal@2026"

DEPARTMENTS = [
    ("Information Technology", "IT", "BS IT and computing programmes"),
    ("Hostel & Student Affairs", "HSA", "Residence, mess and student welfare"),
    ("Administration & Accounts", "ADM", "Admissions, fees, records and general administration"),
]

STUDENTS = [
    ("Abdul Wahab", "abdul.wahab@student.mao.edu.pk", "BSIT-22-084600", "IT"),
    ("Mohsin Ali", "mohsin.ali@student.mao.edu.pk", "BSIT-22-084561", "IT"),
    ("Ahsan Jaffar", "ahsan.jaffar@student.mao.edu.pk", "BSIT-22-084584", "IT"),
    ("Bilal Hussain", "bilal.hussain@student.mao.edu.pk", "BSCS-23-091204", "HSA"),
    ("Zainab Fatima", "zainab.fatima@student.mao.edu.pk", "BBA-23-077310", "ADM"),
]

HODS = [
    ("Prof. Haseeb Azmat", "haseeb.azmat@mao.edu.pk", "STAFF-IT-001", "IT"),
    ("Dr. Nadia Iqbal", "nadia.iqbal@mao.edu.pk", "STAFF-HSA-002", "HSA"),
]

ADMIN = ("Principal M.A.O College", "principal@mao.edu.pk", "STAFF-ADM-000")

# (subject, description, category, department code, anonymous, target status)
COMPLAINTS = [
    (
        "Incorrect marks displayed for Database Systems",
        "My mid-term result for the Database Systems course shows 12 marks, but the "
        "answer sheet shown during paper viewing totalled 34. Please have the result "
        "rechecked and corrected on the portal.",
        ComplaintCategory.ACADEMIC, "IT", False, ComplaintStatus.CLOSED,
    ),
    (
        "Lab computers missing required development software",
        "Half of the machines in Lab 2 do not have Python or Visual Studio Code "
        "installed, so the programming lab session cannot be completed on time.",
        ComplaintCategory.ACADEMIC, "IT", False, ComplaintStatus.RESOLVED,
    ),
    (
        "Attendance not recorded for three lectures",
        "My attendance for the Web Engineering lectures held on the 4th, 6th and 11th "
        "is missing from the portal even though I was present and signed the sheet.",
        ComplaintCategory.ACADEMIC, "IT", True, ComplaintStatus.IN_PROGRESS,
    ),
    (
        "Projector in Room 14 has been broken for two weeks",
        "The projector in classroom 14 does not switch on. Lecturers have to use the "
        "whiteboard which makes the code demonstrations impossible to follow.",
        ComplaintCategory.ACADEMIC, "IT", False, ComplaintStatus.ASSIGNED,
    ),
    (
        "Timetable clash between two core courses",
        "Software Engineering and Operating Systems are both scheduled at 10:00 on "
        "Tuesday, so students of the 6th semester cannot attend both classes.",
        ComplaintCategory.ACADEMIC, "IT", False, ComplaintStatus.SUBMITTED,
    ),
    (
        "Quiz result not uploaded on the portal",
        "The result of the second quiz of Computer Networks has still not been "
        "uploaded although it was conducted more than three weeks ago.",
        ComplaintCategory.ACADEMIC, "IT", True, ComplaintStatus.SUBMITTED,
    ),
    (
        "No hot water supply in Block B washrooms",
        "There has been no hot water in the Block B washrooms for the last ten days. "
        "The geyser appears to be out of order and has not been repaired.",
        ComplaintCategory.HOSTEL, "HSA", False, ComplaintStatus.RESOLVED,
    ),
    (
        "Poor quality of food served in the mess",
        "The quality of the food served in the hostel mess has dropped considerably. "
        "Several residents have complained of stomach problems this month.",
        ComplaintCategory.HOSTEL, "HSA", True, ComplaintStatus.IN_PROGRESS,
    ),
    (
        "Ceiling fan in room 212 is not working",
        "The ceiling fan in hostel room 212 stopped working four days ago. The room "
        "becomes unbearable in the afternoon and study becomes impossible.",
        ComplaintCategory.HOSTEL, "HSA", False, ComplaintStatus.ASSIGNED,
    ),
    (
        "Laundry service is not collecting clothes on schedule",
        "The hostel laundry has not collected clothes on the announced schedule for "
        "three consecutive weeks, and no revised timing has been shared.",
        ComplaintCategory.HOSTEL, "HSA", False, ComplaintStatus.SUBMITTED,
    ),
    (
        "Noise from the common room after midnight",
        "Loud music is played in the common room well past midnight which disturbs "
        "residents preparing for their examinations.",
        ComplaintCategory.HOSTEL, "HSA", True, ComplaintStatus.CANCELLED,
    ),
    (
        "Fee challan shows a duplicate charge",
        "My fee challan for this semester contains the library fine twice. I have "
        "already paid the fine last semester and hold the receipt.",
        ComplaintCategory.ADMINISTRATION, "ADM", False, ComplaintStatus.CLOSED,
    ),
    (
        "Character certificate has not been issued",
        "I applied for a character certificate over one month ago through the "
        "administration office and have received no response despite reminders.",
        ComplaintCategory.ADMINISTRATION, "ADM", False, ComplaintStatus.IN_PROGRESS,
    ),
    (
        "Library issue counter closes without notice",
        "The library issue counter is frequently closed during the advertised opening "
        "hours, so books cannot be borrowed before the weekend.",
        ComplaintCategory.ADMINISTRATION, "ADM", True, ComplaintStatus.ASSIGNED,
    ),
    (
        "Student ID card reissue request pending",
        "My student card was lost and the reissue request submitted three weeks ago is "
        "still pending, which prevents me from entering the examination hall.",
        ComplaintCategory.ADMINISTRATION, "ADM", False, ComplaintStatus.SUBMITTED,
    ),
]

#: The exact chain of transitions needed to reach each target status.
PATHS = {
    ComplaintStatus.SUBMITTED: [],
    ComplaintStatus.CANCELLED: [ComplaintStatus.CANCELLED],
    ComplaintStatus.ASSIGNED: [ComplaintStatus.ASSIGNED],
    ComplaintStatus.IN_PROGRESS: [ComplaintStatus.ASSIGNED, ComplaintStatus.IN_PROGRESS],
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

TRANSITION_NOTES = {
    ComplaintStatus.ASSIGNED: "Assigned for departmental review.",
    ComplaintStatus.IN_PROGRESS: "Investigation has started.",
    ComplaintStatus.RESOLVED: "Issue addressed; awaiting closure.",
    ComplaintStatus.CLOSED: "Complaint closed after confirmation.",
    ComplaintStatus.CANCELLED: "Withdrawn by the complainant.",
}


class Command(BaseCommand):
    help = "Seed the database with a realistic demo dataset."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush-complaints",
            action="store_true",
            help="Delete existing complaints before seeding new ones.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        random.seed(20260806)  # deterministic demo data

        departments = self._seed_departments()
        admin = self._seed_admin()
        hods = self._seed_hods(departments)
        students = self._seed_students(departments)

        if options["flush_complaints"]:
            deleted, _ = Complaint.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"Removed {deleted} complaint object(s)."))

        created = self._seed_complaints(departments, students, hods, admin)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Demo data ready."))
        self.stdout.write(
            f"  departments={len(departments)} admin=1 hods={len(hods)} "
            f"students={len(students)} complaints={created}"
        )
        self.stdout.write("")
        self.stdout.write("  Sign-in credentials (all share the same password):")
        self.stdout.write(f"    password : {DEMO_PASSWORD}")
        self.stdout.write(f"    admin    : {ADMIN[1]}")
        for name, email, identifier, code in HODS:
            self.stdout.write(f"    hod      : {email}  ({code})")
        for name, email, identifier, code in STUDENTS:
            self.stdout.write(f"    student  : {email}  ({identifier})")

    # -- helpers -----------------------------------------------------------
    def _seed_departments(self):
        departments = {}
        for name, code, description in DEPARTMENTS:
            department, created = Department.objects.update_or_create(
                code=code,
                defaults={"name": name, "description": description, "is_active": True},
            )
            departments[code] = department
            self.stdout.write(
                f"{'created' if created else 'updated'} department {code} - {name}"
            )
        return departments

    def _upsert_user(self, *, email, full_name, identifier, role, department):
        user, created = User.objects.update_or_create(
            email=email,
            defaults={
                "username": email,
                "full_name": full_name,
                "identifier": identifier,
                "role": role,
                "department": department,
                "is_active": True,
            },
        )
        user.set_password(DEMO_PASSWORD)
        if role == Role.ADMIN:
            user.is_staff = True
            user.is_superuser = True
        user.save()
        self.stdout.write(f"{'created' if created else 'updated'} {role.lower()} {email}")
        return user

    def _seed_admin(self):
        full_name, email, identifier = ADMIN
        return self._upsert_user(
            email=email,
            full_name=full_name,
            identifier=identifier,
            role=Role.ADMIN,
            department=None,
        )

    def _seed_hods(self, departments):
        return [
            self._upsert_user(
                email=email,
                full_name=full_name,
                identifier=identifier,
                role=Role.HOD,
                department=departments[code],
            )
            for full_name, email, identifier, code in HODS
        ]

    def _seed_students(self, departments):
        return [
            self._upsert_user(
                email=email,
                full_name=full_name,
                identifier=identifier,
                role=Role.STUDENT,
                department=departments[code],
            )
            for full_name, email, identifier, code in STUDENTS
        ]

    def _staff_for(self, code, hods, admin):
        """The HOD who owns a department, falling back to the Principal."""
        for hod in hods:
            if hod.department and hod.department.code == code:
                return hod
        return admin

    def _seed_complaints(self, departments, students, hods, admin):
        created = 0
        now = timezone.now()

        for index, row in enumerate(COMPLAINTS):
            subject, description, category, code, anonymous, target = row
            if Complaint.objects.filter(subject=subject).exists():
                continue

            student = students[index % len(students)]
            department = departments[code]
            staff = self._staff_for(code, hods, admin)
            submitted_at = now - timezone.timedelta(days=len(COMPLAINTS) - index + 2)

            complaint = Complaint(
                subject=subject,
                description=description,
                category=category,
                department=department,
                student=student,
                is_anonymous=anonymous,
                status=ComplaintStatus.SUBMITTED,
                created_at=submitted_at,
            )
            complaint.save()

            ComplaintStatusHistory.objects.create(
                complaint=complaint,
                from_status=ComplaintStatus.SUBMITTED,
                to_status=ComplaintStatus.SUBMITTED,
                changed_by=student,
                note="Complaint submitted.",
            )

            for step, next_status in enumerate(PATHS[target], start=1):
                actor = student if next_status == ComplaintStatus.CANCELLED else staff
                complaint.transition_to(
                    next_status, actor=actor, note=TRANSITION_NOTES[next_status]
                )
                if next_status == ComplaintStatus.ASSIGNED:
                    complaint.assigned_to = staff
                    complaint.save(update_fields=["assigned_to"])

            # Backdate the timestamps so analytics have a realistic spread.
            updates = {"created_at": submitted_at}
            if complaint.resolved_at:
                updates["resolved_at"] = submitted_at + timezone.timedelta(
                    hours=random.randint(18, 120)
                )
            if complaint.closed_at:
                base = updates.get("resolved_at", submitted_at)
                updates["closed_at"] = base + timezone.timedelta(
                    hours=random.randint(2, 36)
                )
            Complaint.objects.filter(pk=complaint.pk).update(**updates)

            if target in {
                ComplaintStatus.IN_PROGRESS,
                ComplaintStatus.RESOLVED,
                ComplaintStatus.CLOSED,
            }:
                ComplaintRemark.objects.create(
                    complaint=complaint,
                    author=staff,
                    text="Thank you for reporting this. The department is looking into "
                    "it and you will be updated as soon as there is progress.",
                    is_internal=False,
                )

            created += 1
            self.stdout.write(f"created complaint {complaint.reference} [{target}]")

        return created
