# Deploying to Vercel

**Online Complaint Registration & Management System**

This puts the portal on a public HTTPS URL for free, with no credit card. Budget
about 20 minutes the first time.

Everything used here is free: Vercel's Hobby plan for hosting, and Neon (or
Supabase) for the database. Neither asks for payment details.

---

## Read this before you start

Vercel does not run a normal server. It runs your code as a **serverless
function** that starts, answers one request, and is thrown away. Three things
follow from that, and the project has already been adapted for all three:

| Serverless reality | What would break | How this project handles it |
|---|---|---|
| The filesystem is read-only | SQLite would lose every complaint | A hosted Postgres database is required, and the app refuses to start without one |
| The filesystem is read-only | Uploaded attachments would vanish | Attachment bytes are stored in the database (`complaints/storage.py`) |
| The process freezes after responding | Notification email on a background thread might never send | Email is sent inline on Vercel |

You do not have to do anything about these — they are listed so the design makes
sense, and so you can explain it if you are asked.

**One thing you must do yourself:** Vercel has no shell, so it cannot run
`migrate` for you. You run it once from your own machine against the same
database (Step 4).

---

## Step 1 — Create the free database

Neon is the smoothest option. Supabase works identically if you prefer it.

1. Go to <https://neon.tech> and sign up (GitHub login works; no card).
2. Create a project — any name, e.g. `ocr-portal`.
3. On the dashboard, find **Connection string** and copy it. It looks like:

   ```
   postgresql://neondb_owner:AbC123xyz@ep-cool-lab-12345678.eu-central-1.aws.neon.tech/neondb?sslmode=require
   ```

**Two details worth getting right:**

* Choose the **Pooled connection** string if Neon offers the choice. Serverless
  functions open many short connections, and the pooler is built for that.
* Keep `?sslmode=require` at the end. The app adds it if missing, but hosted
  Postgres will refuse a plaintext connection.

Treat this string like a password — it grants full access to your database.

---

## Step 2 — Push the project to GitHub

Vercel deploys from a Git repository.

```bash
git remote add origin https://github.com/<your-username>/<your-repo>.git
git branch -M main
git push -u origin main
```

If the repo already exists on GitHub, just `git push`.

> `.gitignore` already excludes `.env`, `db.sqlite3` and `.venv`, so no secrets
> or local artefacts are published.

---

## Step 3 — Import the project into Vercel

1. Go to <https://vercel.com> and sign up with GitHub (no card).
2. **Add New… → Project**, then import your repository.
3. Leave the framework preset as **Other**. `vercel.json` already tells Vercel
   what to do; do not set a build or output directory.
4. Before clicking Deploy, open **Environment Variables** and add these four:

| Name | Value |
|---|---|
| `DATABASE_URL` | the connection string from Step 1 |
| `SECRET_KEY` | a fresh random key — generate one below |
| `DJANGO_SETTINGS_MODULE` | `config.settings.vercel` |
| `PYTHONPATH` | `.` |

Generate a `SECRET_KEY` on your own machine:

```bash
.venv/Scripts/python.exe -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
```

Never reuse the development key, and never commit this value.

5. Click **Deploy** and wait for the build (roughly 1–2 minutes).

The first visit will show an error page — expected: the database is empty until
Step 4.

### Optional: real email

Leave these out and email is written to the Vercel logs instead of being sent,
which is fine for a demo. To send real messages, add:

| Name | Value |
|---|---|
| `EMAIL_BACKEND` | `django.core.mail.backends.smtp.EmailBackend` |
| `EMAIL_HOST_USER` | your Gmail address |
| `EMAIL_HOST_PASSWORD` | a Gmail **App Password** (free — see README) |
| `DEFAULT_FROM_EMAIL` | `Complaint Portal <your.address@gmail.com>` |

---

## Step 4 — Prepare the database (once)

Vercel cannot do this for you. Run it from your own machine, pointing at the
same database.

**Windows (Command Prompt):**

```bat
set DATABASE_URL=postgresql://neondb_owner:PASSWORD@HOST/neondb?sslmode=require
.venv\Scripts\python.exe manage.py bootstrap_remote --seed
```

**macOS / Linux:**

```bash
export DATABASE_URL='postgresql://neondb_owner:PASSWORD@HOST/neondb?sslmode=require'
.venv/bin/python manage.py bootstrap_remote --seed
```

Use the **exact same string** you gave Vercel, quotes included on Unix.

You should see:

```
Target database
  engine : postgresql
  name   : neondb
  host   : ep-cool-lab-12345678.eu-central-1.aws.neon.tech

Checking connectivity ...
  Connection OK.
Applying migrations ...
  Migrations applied.
Loading demo data ...
  Demo data loaded.

Database is ready.
  departments=3 users=8 complaints=15
```

Drop `--seed` if you want an empty system with no demo accounts. You will then
need a real administrator:

```
.venv\Scripts\python.exe manage.py createsuperuser
```

The command refuses to run against your local SQLite file by mistake, and it is
safe to re-run.

---

## Step 5 — Open the portal

Visit the URL Vercel gave you, e.g. `https://your-project.vercel.app/`.

Sign in with the seeded accounts (password `Portal@2026`):

| Role | Email |
|---|---|
| Principal / Admin | `principal@mao.edu.pk` |
| HOD (IT) | `haseeb.azmat@mao.edu.pk` |
| Student | `abdul.wahab@student.mao.edu.pk` |

> **Change these passwords immediately.** The site is public. Sign in as the
> Principal, go to **Users**, and set a new password on every account you keep —
> or deploy without `--seed` and create your own.

---

## Redeploying after a change

Push to GitHub and Vercel rebuilds automatically:

```bash
git add -A
git commit -m "Describe your change"
git push
```

If a change adds or alters a model, re-run the migration step afterwards:

```
set DATABASE_URL=postgresql://...
.venv\Scripts\python.exe manage.py migrate
```

---

## Troubleshooting

### The page shows `DATABASE_URL is not set`

The variable is missing or misspelled in Vercel. Go to **Settings → Environment
Variables**, confirm `DATABASE_URL` is present for the **Production**
environment, then **Deployments → ⋯ → Redeploy**. Environment variable changes
only take effect on a new deployment.

### `relation "accounts_user" does not exist`

Step 4 has not been run, or it ran against a different database. Re-run
`bootstrap_remote` with the exact connection string configured in Vercel.

### `500` on every page, `DisallowedHost` in the logs

You are using a custom domain. Add it to an `ALLOWED_HOSTS` environment variable
(comma-separated, no scheme), e.g. `complaints.mao.edu.pk`, and redeploy.
`*.vercel.app` is already trusted.

### CSRF verification failed on the login form

Add the site's origin to `CSRF_TRUSTED_ORIGINS`, including the scheme:
`https://complaints.mao.edu.pk`. Only needed for custom domains.

### First request after a while is slow

Two free-tier behaviours stacking up: Vercel cold-starts an idle function, and
Neon suspends an idle database after about five minutes. The first request can
take a few seconds; subsequent ones are fast. Nothing is wrong.

### `FUNCTION_INVOCATION_TIMEOUT`

A Hobby-plan function is capped at 10 seconds. This normally only happens when a
cold start coincides with a suspended database. Reload once. If it persists,
check that you used Neon's **pooled** connection string.

### Deployment fails during build

Open the build log in Vercel. The usual cause is a package failing to install —
confirm `requirements.txt` is committed and unmodified.

---

## What is different about the Vercel deployment

Worth knowing, and worth being able to explain:

1. **Attachments are stored in the database, not on disk.** Necessary, and fine
   at this scale (5 MB per file, 5 files per complaint). A large institution
   with years of uploads should move to object storage.
2. **Neon's free tier gives 0.5 GB.** Ample for a demo or a small college; keep
   an eye on it if attachments pile up.
3. **Email is sent inline**, adding roughly a second to the request that
   triggers it. Failures are still recorded and never break the request.
4. **Static files are served from the function** rather than a build artefact,
   because Vercel's Python builder runs no `collectstatic` step. Slightly slower
   than a CDN, entirely correct, and free.
5. **`db.sqlite3` is ignored in deployment.** Local data does not travel to the
   deployed site; the two are separate systems.

## Deploying elsewhere instead

Vercel is a good fit for a demo URL. For a college server that runs continuously,
the Docker path in [README.md](README.md) is simpler and has none of the
serverless constraints — SQLite works, files live on disk, and email can stay on
a background thread. Both are free.

---

## What was verified before publishing this guide

The deployment path is covered by 20 automated tests in
`tests/test_deployment.py`, which run as part of the normal suite:

* the WSGI entry point in `api/index.py` imports and serves real requests
* `/accounts/login/` returns 200 and static CSS/JS are served with no
  `collectstatic` step
* plain HTTP redirects to HTTPS; an unknown `Host` header is rejected with 400
* HSTS, `nosniff` and `X-Frame-Options` are present on real responses
* booting without `DATABASE_URL` fails loudly instead of silently losing data
* `DATABASE_URL` correctly overrides the SQLite default

`python manage.py check --deploy --settings=config.settings.vercel` reports no
issues.

**Not verified:** an actual deployment to Vercel with a live Neon database. That
needs accounts on both services, which only you can create. Everything that can
be checked without them has been.
