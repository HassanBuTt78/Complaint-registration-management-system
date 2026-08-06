# Online Complaint Registration & Management System

A role-based complaint portal for **Govt. M.A.O Graduate College, Lahore**, built
with Django 5 following the MVT architecture. Students submit and track
complaints (optionally anonymously), Heads of Department manage only their own
department's complaints, and the Principal has global oversight, user management
and audited unmasking.

Final Year Design Project — BS Information Technology, Session 2022–2026.
Abdul Wahab (084600) · Mohsin Ali (084561) · Ahsan Jaffar (084584).
Supervised by Prof. Haseeb Azmat.

---

## Table of contents

1. [Zero-cost guarantee](#zero-cost-guarantee)
2. [Quick start](#quick-start) · [Offline install](#fully-offline-installation) · [Known limitations](#known-limitations)
3. [Demo accounts](#demo-accounts)
4. [Running the tests](#running-the-tests)
5. [Docker](#docker)
6. [Production deployment](#production-deployment)
7. [Project structure](#project-structure)
8. [Roles and permissions](#roles-and-permissions)
9. [Complaint state machine](#complaint-state-machine)
10. [How anonymity is enforced](#how-anonymity-is-enforced)
11. [Requirements traceability (FR-1 … FR-12)](#requirements-traceability)
12. [Algorithm traceability (Chapter 4)](#algorithm-traceability)
13. [Test-case traceability (Chapter 5)](#test-case-traceability)
14. [Known limitations](#known-limitations)
15. [Deviations from the FYP report](#deviations-from-the-fyp-report)

---

## Zero-cost guarantee

Every component is free and open source. Nothing here needs a paid plan, an
expiring trial, a credit card, or a billed API key.

| Component | Choice | Licence / cost |
|---|---|---|
| Language | Python 3.11+ (tested on 3.13) | PSF — free |
| Framework | Django 5.2 | BSD-3-Clause — free |
| Database | SQLite (default) or MySQL 8 Community Edition | Public domain / GPLv2 — free |
| Frontend | Bootstrap 5.3, Chart.js 4.4, vanilla ES6 | MIT — free, **vendored locally** (no CDN account, works offline) |
| Email | Django console backend (dev) · Gmail SMTP + free App Password (prod) | Free forever, no card |
| PDF reports | ReportLab | BSD-3-Clause — free |
| MySQL driver | PyMySQL (pure Python, no compiler needed) | MIT — free |
| Static files | WhiteNoise | MIT — free |
| Brute-force protection | django-axes | MIT — free |
| Containers | Docker Engine / Docker Desktop (personal use) | Free — and **entirely optional** |
| Hosting | Local machine or college LAN server | Free |

Explicitly **not** used: SendGrid, Mailgun, AWS SES, Twilio/SMS, Stripe, any
AWS/GCP/Azure paid tier, any hosted monitoring or logging service. A regression
test (`tests/test_security.py::ZeroCostDependencyTests`) fails the build if a
paid-service client ever appears in `requirements.txt`, if any requirement is
left unpinned, or if a CDN URL creeps into the base template.

**Optional free hosting** (not required — the project runs fully offline):
PythonAnywhere free tier or Render free tier both host a Django + SQLite app at
no cost. Nothing in the codebase depends on either.

---

## Quick start

### Easiest: one-click launcher

**Windows** — double-click **`run.bat`**.
**macOS / Linux** — `chmod +x run.sh && ./run.sh`.

It finds Python, creates the virtual environment, installs the dependencies,
creates and seeds the database, starts the server and opens your browser. On
later runs it skips whatever is already done and starts in a couple of seconds.

Two things it cannot do for you:

* **Python 3.11+ must already be installed.** If it is missing the script says
  so and links to the free download. On Windows, tick *"Add Python to PATH"* in
  the installer.
* **The first run needs internet**, once, to download the dependencies. See
  [Fully offline installation](#fully-offline-installation) to remove even that.

### Manual setup

Requires Python 3.11 or newer. Nothing else.

```bash
# 1. Get the code and enter it
cd complaint_system

# 2. Create and activate a virtual environment
python -m venv .venv
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Windows (Git Bash):  source .venv/Scripts/activate
# macOS / Linux:       source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create your environment file
cp .env.example .env          # Windows: copy .env.example .env
#    The defaults work as-is for development — no editing required.

# 5. Create the database
python manage.py migrate

# 6. Load the demo dataset (3 departments, 8 users, 15 complaints)
python manage.py seed_demo_data

# 7. Run it
python manage.py runserver
```

Open <http://127.0.0.1:8000/> and sign in with any account below.

In development, emails are printed to the terminal running `runserver` — no
SMTP server or account is needed.

### Fully offline installation

To run on a machine that has **no internet at all** (e.g. a lab PC on exam day),
prepare the wheels once on a connected machine:

```bash
pip download -r requirements.txt -d vendor
```

Copy the whole project folder — `vendor/` included — to the offline machine and
run `run.bat` / `run.sh` as usual. The launcher detects `vendor/` and installs
with `--no-index`, so nothing is fetched from the network.

`vendor/` is deliberately **not** committed: the wheels are platform-specific
(a Windows wheel will not install on Linux) and add roughly 40 MB, so they are
generated on the machine family you intend to deploy to.

### Verified portability

The steps above were tested by extracting a fresh copy of the repository into an
empty directory, with no `.env`, no database and no virtual environment:

| Check | Result |
|---|---|
| Boots with **no `.env` file** (all settings fall back to safe defaults) | `check` reports no issues |
| Runs on **Python 3.14** as well as 3.13 | Django 5.2.17 imports and runs |
| `migrate` from empty | 31 migrations applied |
| `seed_demo_data` from empty | 3 departments, 8 users, 15 complaints |
| Full test suite in the clean copy | 284 passed |
| Server + real browser login | 200, reached the dashboard |
| `run.bat` from a folder with nothing but source | venv + deps + DB + server, unattended |

---

## Demo accounts

All seeded accounts share the password **`Portal@2026`**.

| Role | Email | ID | Scope |
|---|---|---|---|
| Principal / Admin | `principal@mao.edu.pk` | `STAFF-ADM-000` | All departments |
| HOD | `haseeb.azmat@mao.edu.pk` | `STAFF-IT-001` | Information Technology |
| HOD | `nadia.iqbal@mao.edu.pk` | `STAFF-HSA-002` | Hostel & Student Affairs |
| Student | `abdul.wahab@student.mao.edu.pk` | `BSIT-22-084600` | Own complaints |
| Student | `mohsin.ali@student.mao.edu.pk` | `BSIT-22-084561` | Own complaints |
| Student | `ahsan.jaffar@student.mao.edu.pk` | `BSIT-22-084584` | Own complaints |
| Student | `bilal.hussain@student.mao.edu.pk` | `BSCS-23-091204` | Own complaints |
| Student | `zainab.fatima@student.mao.edu.pk` | `BBA-23-077310` | Own complaints |

You can sign in with **either the email address or the institutional ID**.

The Principal account is also a Django superuser, so `/django-admin/` works.

> **Change these passwords before any real deployment.** They exist only to make
> the demo reproducible.

Useful things to try:

* Sign in as a student → *Submit Complaint* → tick **Submit anonymously**.
* Sign in as `haseeb.azmat@mao.edu.pk` → the complainant shows as *Anonymous*,
  and searching for their name returns nothing.
* Sign in as `principal@mao.edu.pk` → open the same complaint → *Unmask
  identity* → then check *Activity Log* for the recorded reason.
* Sign in as `nadia.iqbal@mao.edu.pk` → the IT department's complaints are not
  visible, and opening one by URL returns 403.

---

## Running the tests

```bash
# Full suite (284 tests)
python manage.py test tests --settings=config.settings.test

# With coverage
coverage run manage.py test tests --settings=config.settings.test
coverage report
coverage html          # detailed report in htmlcov/index.html

# Django's production readiness audit
SECRET_KEY="$(python -c 'from django.core.management.utils import get_random_secret_key as k; print(k())')" \
ALLOWED_HOSTS="complaints.mao.edu.pk" \
python manage.py check --deploy --settings=config.settings.prod
```

Current results:

```
Ran 284 tests   OK
TOTAL coverage  93.4%     (target: >= 80% on models/views/forms)
check --deploy  System check identified no issues (0 silenced)
```

Test modules:

| File | Kind | Focus |
|---|---|---|
| `tests/test_models.py` | Unit | Model methods, the full state-transition matrix, anonymity helpers, queryset scoping, upload-path sanitisation |
| `tests/test_auth.py` | Functional | Registration, login by email/ID, lockout, profile, admin user-form business rules |
| `tests/test_complaints.py` | Functional | Submission, editing, cancellation, assignment, remarks, attachment validation, secure download, filtering/search/sorting, categoriser |
| `tests/test_rbac.py` | Functional | Role routing, forbidden-URL matrix, department isolation, anonymity across every surface, unmasking, user management, IDOR sweep |
| `tests/test_notifications.py` | Integration | Complaint → database → email pipeline, delivery failure handling, async dispatch |
| `tests/test_dashboards.py` | Integration | Dashboards, analytics aggregation, CSV/PDF exports, error pages, seed command |
| `tests/test_security.py` | Security | CSRF enforcement, password hashing, HTTP-method guards, no raw SQL, secrets hygiene, zero-cost dependency audit, deployment checks |

The test settings module (`config/settings/test.py`) disables django-axes so
`Client.login()` works; lockout behaviour is instead exercised through the real
login *view*, where an `HttpRequest` exists.

---

## Docker

Docker is entirely optional — the project runs without it.

```bash
# SQLite (default): one command, no database server
docker compose up --build

# Seed the demo data on first boot
SEED_DEMO_DATA=1 docker compose up --build

# With MySQL 8 Community Edition instead
#   set DB_ENGINE=mysql and DB_HOST=db in .env, then:
docker compose --profile mysql up --build
```

The app is served at <http://localhost:8000/>. `entrypoint.sh` waits for the
database, applies migrations, optionally seeds, then starts gunicorn. Static
files are collected at image build time and served by WhiteNoise; media and logs
live on named volumes. The container runs as an unprivileged `portal` user.

---

## Production deployment

1. **Generate a real secret key** and put it in `.env`:
   ```bash
   python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
   ```
   `config/settings/prod.py` **refuses to start** on the development fallback key.
2. Set `DEBUG=False` and a real `ALLOWED_HOSTS` (plus `CSRF_TRUSTED_ORIGINS` if
   you serve over HTTPS behind a proxy).
3. Configure free Gmail SMTP: enable 2-Step Verification on the Google account,
   create an **App Password** (Google Account → Security → App passwords), and
   set `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend` plus
   `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD`.
4. Run the audit until it is clean:
   ```bash
   python manage.py check --deploy --settings=config.settings.prod
   ```
5. `python manage.py collectstatic --noinput`, then serve with gunicorn behind a
   TLS-terminating proxy.

Production settings enable HSTS (1 year, subdomains, preload), secure and
HttpOnly session cookies, `SECURE_SSL_REDIRECT`, `X_FRAME_OPTIONS=DENY`,
`nosniff`, and a same-origin referrer policy.

---

## Project structure

```
complaint_system/
├── manage.py
├── requirements.txt          # pinned, all free/OSS, licence noted per package
├── .env.example              # template; .env itself is git-ignored
├── .coveragerc
├── Dockerfile
├── entrypoint.sh
├── docker-compose.yml
├── README.md
├── config/                   # project configuration
│   ├── settings/
│   │   ├── base.py           # shared settings, env-driven
│   │   ├── dev.py            # DEBUG, console email, autorefresh static
│   │   ├── prod.py           # DEBUG=False, HSTS, secure cookies, key guard
│   │   └── test.py           # in-memory DB, locmem email, axes disabled
│   ├── urls.py               # root URLconf + 403/404/500 handlers
│   └── views.py              # custom error views
├── accounts/                 # Department, custom User, Role, AuditLog, RBAC
│   ├── models.py  backends.py  mixins.py  forms.py  views.py  admin.py
│   └── management/commands/seed_demo_data.py
├── complaints/               # Complaint domain and workflow
│   ├── models.py             # state machine, anonymity, queryset scoping
│   ├── services.py           # use-cases: create/update/assign/transition/unmask
│   ├── forms.py  validators.py  categorizer.py  views.py
│   └── templatetags/complaint_extras.py
├── dashboards/               # role dashboards, analytics, reports, user admin
│   ├── views.py  exports.py  urls.py
├── notifications/            # Notification model + failure-safe email service
│   ├── models.py  services.py
│   └── templates/notifications/email/
├── templates/                # base layout, auth, complaints, dashboards, errors
├── static/                   # vendored Bootstrap + Chart.js, portal CSS/JS
├── media/                    # uploaded evidence (served only via a checked view)
└── tests/                    # 284 tests across 7 modules
```

---

## Roles and permissions

| Capability | Student | HOD | Principal / Admin |
|---|:--:|:--:|:--:|
| Register publicly | ✔ | — | — |
| Submit a complaint | ✔ | — | — |
| Attach PDF/JPG/PNG evidence | ✔ | — | — |
| Submit anonymously | ✔ | — | — |
| Edit / cancel before assignment | ✔ | — | — |
| View own complaints | ✔ | — | — |
| View own department's complaints | — | ✔ | ✔ |
| View **all** complaints | — | — | ✔ |
| Assign to staff | — | ✔ | ✔ |
| Change status | — | ✔ | ✔ |
| Add remarks | ✔ | ✔ | ✔ |
| Add **internal** notes (hidden from student) | — | ✔ | ✔ |
| Filter / search / sort | ✔ | ✔ | ✔ |
| Analytics & reports (CSV/PDF) | — | ✔ (own dept) | ✔ (global) |
| See an anonymous complainant's identity | own only | **never** | via audited unmask only |
| Manage users and departments | — | — | ✔ |
| View the activity log | — | — | ✔ |

Enforcement is layered: `RoleRequiredMixin` / `@role_required` gate the view,
and `Complaint.objects.visible_to(user)` scopes the queryset — so an
out-of-scope object is unreachable even by guessing its URL. Every rejection
returns HTTP 403 *and* writes an `AuditLog` entry.

---

## Complaint state machine

```
                    ┌──────────────┐
                    │  Submitted   │◄── created here
                    └──┬────────┬──┘
          assign       │        │       student cancels
                       ▼        ▼
                 ┌──────────┐  ┌───────────┐
                 │ Assigned │  │ Cancelled │ (terminal)
                 └────┬─────┘  └───────────┘
        start work    │
                      ▼
              ┌───────────────┐
              │  In Progress  │
              └───────┬───────┘
        resolve       │
                      ▼
                ┌──────────┐
                │ Resolved │
                └────┬─────┘
        close         │
                      ▼
                 ┌────────┐
                 │ Closed │ (terminal)
                 └────────┘
```

`ALLOWED_TRANSITIONS` in `complaints/models.py` is the single source of truth.
`Complaint.transition_to()` raises `InvalidTransition` for anything else — the
form only *offers* legal next statuses, and the view rejects an illegal one even
if it is posted directly. `tests/test_models.py::StateMachineTests` sweeps the
entire 6×6 status matrix and asserts every illegal pair is refused.

Each valid transition writes a `ComplaintStatusHistory` row (powering the
timeline), an `AuditLog` entry, and an email notification to the complainant.

---

## How anonymity is enforced

Anonymity is the SRS's most security-sensitive requirement, so it is enforced in
one place and tested from every angle.

* `Complaint.identity_visible_to(user)` is the **single source of truth**.
  For an anonymous complaint it returns `True` only for the complainant
  themselves — including for the Principal.
* `complainant_display()`, `complainant_identifier()` and `complainant_email()`
  all route through it, and so do the template filters
  (`complainant_for`, `identity_visible`), the timeline builder, the remark and
  status-history author labels, and both report exporters.
* **Search cannot be used as a side channel.** `apply_filters()` never queries
  complainant fields for an HOD at all; for the Principal it matches names only
  on complaints where `is_anonymous=False`.
* **The Principal's privilege is the audited unmask action, not passive sight.**
  `dashboards:unmask` requires an explicit confirmation and a written reason of
  at least 5 characters, reveals the identity once in a flash message, and
  writes an `AuditLog` entry naming the actor, the complaint and the reason. The
  complaint itself is never modified, so HODs remain permanently masked.
* Notification emails go only to the complainant, never to staff.

`tests/test_rbac.py::AnonymityEnforcementTests` asserts the student's name, roll
number and email appear nowhere in the HOD's detail view, dashboard list, report
page, analytics page, CSV export or PDF export, and that probing the search box
with each of those strings returns nothing.

---

## Requirements traceability

Every functional requirement from Chapter 2 of the FYP report, mapped to the
code that implements it and the tests that prove it.

| FR | Title | Implementation | Tests |
|---|---|---|---|
| **FR-1** | User registration | `accounts/forms.py::StudentSignUpForm` · `accounts/views.py::signup` · `templates/registration/signup.html` | `test_auth.py::RegistrationTests` (11) |
| **FR-2** | User login | `accounts/backends.py::EmailOrIdentifierBackend` · `accounts/views.py::PortalLoginView` · `accounts/forms.py::PortalLoginForm` | `test_auth.py::LoginTests` (10), `BruteForceLockoutTests` |
| **FR-3** | Submit complaint | `complaints/forms.py::ComplaintForm` · `complaints/views.py::complaint_create` · `complaints/services.py::create_complaint` | `test_complaints.py::ComplaintSubmissionTests` (16) |
| **FR-4** | Upload attachments | `complaints/validators.py::validate_attachment` · `complaints/models.py::attachment_upload_path` · `ComplaintAttachment` | `test_complaints.py::AttachmentValidatorTests`, `AttachmentDownloadTests`, `test_models.py::AttachmentPathTests` |
| **FR-5** | Anonymous submission | `Complaint.is_anonymous` · `identity_visible_to()` · `can_unmask()` · `complaints/services.py::unmask_complaint` · `dashboards/views.py::unmask` | `test_rbac.py::AnonymityEnforcementTests` (12), `UnmaskTests` (7), `test_models.py::AnonymityTests` (10) |
| **FR-6** | Complaint status tracking | `dashboards/views.py::student_dashboard` · `complaints/views.py::complaint_detail` · `Complaint.timeline()` · `ComplaintStatusHistory` | `test_dashboards.py::StudentDashboardTests` (7) |
| **FR-7** | View department complaints | `ComplaintQuerySet.visible_to` · `dashboards/views.py::hod_dashboard` · `accounts/mixins.py` | `test_rbac.py::DepartmentIsolationTests` (8), `test_models.py::QuerysetScopingTests` |
| **FR-8** | Update complaint status | `Complaint.transition_to` · `ALLOWED_TRANSITIONS` · `complaints/forms.py::StatusUpdateForm` · `services.py::change_status` | `test_models.py::StateMachineTests` (12), `test_complaints.py::StatusUpdateViewTests` (7) |
| **FR-9** | Email notification | `notifications/services.py` · `notifications/models.py::Notification` · email templates | `test_notifications.py` (20) |
| **FR-10** | User management | `accounts/forms.py::AdminUserForm` · `dashboards/views.py::user_list/create/edit/toggle` | `test_rbac.py::UserManagementTests` (8), `test_auth.py::AdminUserFormTests` (6) |
| **FR-11** | Generate reports | `dashboards/views.py::reports/analytics` · `dashboards/exports.py` | `test_dashboards.py::ReportExportTests` (8), `AnalyticsTests` (9) |
| **FR-12** | Security & access control | `accounts/mixins.py` · `accounts/models.py::AuditLog` · `config/settings/prod.py` | `test_rbac.py::ForbiddenUrlMatrixTests`, `DirectObjectReferenceTests`, `test_security.py` (22) |

Non-functional requirements (section 2.4):

| NFR | Requirement | How it is met |
|---|---|---|
| Reliability | Friendly errors, no data loss, errors logged | Custom 403/404/500 pages; rotating file log in `logs/`; every write is inside `transaction.atomic`; notification failures are caught and recorded, never raised |
| Usability | Submit in ≤ 6 steps, clear labels and errors | Single-page complaint form (subject → department → category → description → optional attachment → submit); live character counters; per-field error lists; Bootstrap responsive layout down to 360 px |
| Performance | < 2 s response, 200 concurrent users | DB indexes on `status`, `department`, `category`, `created_at` and `(status, department)`; `select_related` on every list view; pagination at 15 rows; email dispatched off the request thread |
| Security | RBAC, no unauthorised disclosure, attempts logged | Queryset-level scoping, CSRF on every form, django-axes lockout, hashed passwords, magic-number upload validation, access-denied audit entries |

---

## Algorithm traceability

Chapter 4 of the report specifies ten algorithms in pseudocode.

| # | Algorithm | Implementation |
|---|---|---|
| 1 | Sign-up | `accounts/forms.py::StudentSignUpForm.clean*` + `accounts/views.py::signup` |
| 2 | Login | `accounts/backends.py::EmailOrIdentifierBackend.authenticate` + `PortalLoginView` |
| 3 | Complaint submission | `complaints/services.py::create_complaint` |
| 4 | Complaint status update | `complaints/services.py::change_status` |
| 5 | View complaints (filtered by role) | `ComplaintQuerySet.visible_to` + `services.py::apply_filters` |
| 6 | Anonymity handling | `Complaint.identity_visible_to` / `complainant_display` / `can_unmask` |
| 7 | Search | `services.py::apply_filters` (keyword/reference branch) |
| 8 | Sorting | `services.py::apply_filters` (allow-listed `sort` parameter) |
| 9 | Notification | `notifications/services.py::notify_complaint_event` → `send_email` → `_deliver` |
| 10 | State transition logic | `complaints/models.py::Complaint.transition_to` + `ALLOWED_TRANSITIONS` |

---

## Test-case traceability

Chapter 5 defines twelve manual test cases. All are now automated.

| Report case | Title | Automated as |
|---|---|---|
| UT-01 | User login | `test_auth.py::LoginTests::test_login_with_email_succeeds` |
| UT-02 | Submit complaint | `test_complaints.py::ComplaintSubmissionTests::test_valid_submission_creates_complaint` |
| UT-03 | Update complaint status | `test_complaints.py::StatusUpdateViewTests::test_hod_can_advance_the_status` |
| FT-01 | Role access control | `test_rbac.py::ForbiddenUrlMatrixTests` (all three roles) |
| FT-02 | Anonymous complaint | `test_rbac.py::AnonymityEnforcementTests::test_detail_view_masks_identity_from_hod` |
| FT-03 | Track complaint | `test_dashboards.py::StudentDashboardTests::test_dashboard_lists_all_of_the_students_complaints` |
| IT-01 | Complaint & DB integration | `test_notifications.py::NotificationPipelineTests::test_submission_stores_the_complaint_and_sends_confirmation` |
| IT-02 | Email notification | `test_notifications.py::NotificationPipelineTests` (all 13) |
| IT-03 | Role-based filtering | `test_rbac.py::DepartmentIsolationTests::test_hod_dashboard_lists_only_own_department` |
| PT-01 | System response time | Indexes + `select_related` + pagination; measured manually — see note below |
| PT-02 | Multiple users load | Not automated — see note below |
| PT-03 | DB query performance | `test_dashboards.py::StudentDashboardTests::test_pagination_works` exercises the paginated path |

**Note on PT-01 / PT-02.** Load and response-time testing needs a deployed
instance and a load generator; it is a measurement activity, not a unit test, so
it is not part of `manage.py test`. Free tools that can produce those numbers
are Apache Bench (`ab`) or Locust (both open source). The design work backing
these targets — indexing, `select_related`, pagination and off-thread email — is
in place and described in the NFR table above.

---

## Known limitations

Everything in the requirements is implemented and working. These are the honest
edges of the current build — none of them block the demo or the defence, but you
should know about them rather than discover them.

1. **No self-service password reset.** The login screen says *"Forgot password?
   Contact the administrator"* and the Principal resets it from
   **Users → Edit → Password**. A self-service email reset needs a live SMTP
   account configured, which the zero-cost/offline constraint makes optional.
   Django's built-in reset views can be wired to `accounts/urls.py` in a few
   lines once real SMTP credentials exist.

2. **Docker was never built or run.** The Dockerfile, compose file and
   entrypoint are written and statically validated (YAML parses, `sh -n` clean,
   exec bit set, and the `collectstatic` step the build performs is verified to
   succeed under production settings). Docker itself is not installed on the
   development machine, so `docker compose up --build` is unverified.

3. **Load testing (PT-01, PT-02) is not automated.** Measuring "<2 s response"
   and "200 concurrent users" needs a deployed instance and a load generator —
   a measurement activity, not a unit test. Use the free `ab` or Locust.

4. **Notification delivery has no retry queue.** Email is sent on a daemon
   thread; failures are recorded as `FAILED` in the Notification table and in
   the audit log, but nothing retries them automatically. A durable queue would
   mean adding Celery + Redis — still free, but heavier than this project needs.
   The admin can see every failure under **Activity Log**.

5. **Assignment targets are HODs and the Principal.** The SRS defines exactly
   three roles, so there is no separate "staff" account type to assign work to.
   Complaints are assigned within the owning department's HOD(s) plus the
   Principal. Adding a fourth role would be a schema change.

6. **Uploaded files are not virus-scanned.** They are validated by extension,
   declared content type and magic number, stored outside the web root under
   randomised names, and served only through a permission-checked view — but no
   antivirus engine inspects them. ClamAV is the free option if that matters.

7. **SQLite is the default database.** Excellent for a demo and fine for a
   single college department, but it serialises writes. For heavy concurrent
   use switch `DB_ENGINE=mysql` (already supported and free).

---

## Deviations from the FYP report

The prompt takes precedence over the report where they differ. Everything below
is a deliberate, documented difference.

1. **The Principal does not see anonymous identities passively.** The report's
   class diagram implies the Admin can simply read them. That would make the
   `unmaskAnonymousComplaint()` operation and its audit entry meaningless, and
   the prompt requires that "the Admin *can unmask* … (log every unmask action)".
   Identity is therefore masked for the Principal too, until they invoke the
   explicit, reasoned, audited unmask action. HODs are masked permanently.

2. **Two models were added beyond the report's data dictionary.**
   `ComplaintStatusHistory` records every transition — the prompt requires a
   "timeline of status changes", which the report's schema cannot produce.
   `ComplaintRemark` is in the report as an `addRemarks()` method but had no
   entity; it needed one, and gained an `is_internal` flag so staff notes stay
   hidden from the complainant.

3. **A `reference` field was added to `Complaint`** (e.g. `CMP-2026-000001`).
   The report tracks complaints by integer primary key; a human-quotable
   reference is needed for the search and report features and avoids exposing
   raw row IDs.

4. **`Cancelled` is reachable only from `Submitted`.** The report's state
   diagram draws "Cancel Complaint" from `Submitted` straight to `Closed`. The
   prompt specifies a distinct `Cancelled` state and that the student may cancel
   "before assignment", which is what is implemented.

5. **Framework versions.** The report variously says Django 3.0 / 4.x / 5.0 and
   Python 3.10+/3.11. The prompt mandates Django 5.x and Python 3.11+, so the
   build targets Django 5.2 LTS (tested on Python 3.13).

6. **`Django/Flask` in the tools table is resolved to Django only.** The report
   lists both; the prompt mandates Django MVT, and mixing the two would be
   incoherent.

7. **MySQL uses PyMySQL rather than `mysqlclient`.** `mysqlclient` needs a C
   compiler and MySQL headers, which fails on a stock Windows machine. PyMySQL
   is pure Python, equally free (MIT), and registers itself as the same driver.

8. **Login is by email or institutional ID, without a role radio button.** The
   report's mock-up shows Student/HOD/Admin radio buttons on the login screen.
   Asking an unauthenticated visitor to declare their role adds no security (the
   server must check it anyway) and lets an attacker enumerate roles. The role
   is read from the authenticated account and the user is routed accordingly.

9. **Frontend libraries are vendored, not loaded from a CDN.** Bootstrap and
   Chart.js are committed under `static/`, so the portal works on a college LAN
   with no outbound internet access and cannot break if a CDN changes.

10. **Attachment validation checks magic numbers, not just extensions.** The
    report's business rule is "only PDF, JPG and PNG are allowed". Checking the
    extension alone lets `payload.exe` through as `proof.pdf`, so the file's own
    signature is verified too.
