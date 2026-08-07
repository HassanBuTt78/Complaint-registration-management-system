"""
Prepare a hosted database in one step.

Vercel cannot run management commands for you - a serverless function has no
shell - so the deployed database is prepared from your own machine.

    # Windows (Command Prompt)
    set DATABASE_URL=postgresql://user:pass@host/dbname?sslmode=require
    .venv\\Scripts\\python.exe manage.py bootstrap_remote --seed

    # macOS / Linux
    export DATABASE_URL='postgresql://user:pass@host/dbname?sslmode=require'
    .venv/bin/python manage.py bootstrap_remote --seed

``DATABASE_URL`` is read by ``config/settings/base.py``, so it simply *becomes*
the default database for this one command. That keeps the code path identical to
normal local use - ``migrate`` and ``seed_demo_data`` run exactly as they always
do, with no second database alias to get wrong.

Safe to re-run: migrations are idempotent, and seeding refuses to duplicate an
existing dataset unless you confirm.
"""

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = (
        "Migrate (and optionally seed) the database named by DATABASE_URL - "
        "typically the hosted Postgres instance your deployment uses."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--seed",
            action="store_true",
            help="Also load the demo departments, users and complaints.",
        )
        parser.add_argument(
            "--no-input",
            action="store_true",
            help="Never prompt; proceed even if the database already has data.",
        )
        parser.add_argument(
            "--allow-sqlite",
            action="store_true",
            help="Permit a SQLite target (for rehearsing this command locally).",
        )

    def handle(self, *args, **options):
        config = settings.DATABASES["default"]
        engine = config.get("ENGINE", "")
        is_sqlite = engine.endswith("sqlite3")

        if is_sqlite and not options["allow_sqlite"]:
            raise CommandError(
                "DATABASE_URL is not set, so this would target the local SQLite "
                "file rather than your hosted database.\n\n"
                "Set it first, for example:\n"
                "  Windows : set DATABASE_URL=postgresql://user:pass@host/db\n"
                "  Unix    : export DATABASE_URL='postgresql://user:pass@host/db'\n\n"
                "Then run this command again. (Use --allow-sqlite to rehearse "
                "against the local file on purpose.)\n"
                "See DEPLOY_VERCEL.md for where to find the connection string."
            )

        target = config.get("NAME")
        host = config.get("HOST") or "local file"
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Target database"))
        self.stdout.write(f"  engine : {engine.rsplit('.', 1)[-1]}")
        self.stdout.write(f"  name   : {target}")
        self.stdout.write(f"  host   : {host}")
        self.stdout.write("")

        # --- connectivity -------------------------------------------------
        self.stdout.write("Checking connectivity ...")
        try:
            # `ensure_connection` opens the socket and authenticates without
            # issuing a query, so this probe needs no raw SQL.
            connection.ensure_connection()
        except Exception as exc:
            raise CommandError(
                "Could not connect to the database.\n\n"
                f"  {type(exc).__name__}: {exc}\n\n"
                "Common causes:\n"
                "  - the connection string is missing its password\n"
                "  - '?sslmode=require' is absent (most hosted Postgres needs it)\n"
                "  - the database is paused (free tiers idle after inactivity)\n"
                "  - your network blocks outbound port 5432"
            ) from exc
        self.stdout.write(self.style.SUCCESS("  Connection OK."))

        # --- migrations ---------------------------------------------------
        self.stdout.write("Applying migrations ...")
        call_command("migrate", interactive=False, verbosity=0)
        self.stdout.write(self.style.SUCCESS("  Migrations applied."))

        # --- demo data ----------------------------------------------------
        if options["seed"]:
            from accounts.models import User

            existing = User.objects.count()
            if existing and not options["no_input"]:
                self.stdout.write(
                    self.style.WARNING(
                        f"  This database already holds {existing} user account(s)."
                    )
                )
                answer = input("  Load the demo data anyway? [y/N]: ")
                if answer.strip().lower() not in {"y", "yes"}:
                    self.stdout.write("  Seeding skipped.")
                    self._summary()
                    return

            self.stdout.write("Loading demo data ...")
            call_command("seed_demo_data", verbosity=0)
            self.stdout.write(self.style.SUCCESS("  Demo data loaded."))

        self._summary()

    def _summary(self):
        from accounts.models import Department, User
        from complaints.models import Complaint

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Database is ready."))
        self.stdout.write(
            f"  departments={Department.objects.count()} "
            f"users={User.objects.count()} "
            f"complaints={Complaint.objects.count()}"
        )
        self.stdout.write("")
        self.stdout.write(
            "Next: make sure the same DATABASE_URL is set in your Vercel project "
            "settings, then redeploy."
        )
        self.stdout.write("")
