# How to run this project on any machine

**Online Complaint Registration & Management System**
Govt. M.A.O Graduate College, Lahore

You have the complete project folder. This guide takes you from that folder to a
working portal in your browser. No prior Django knowledge needed.

Everything here is free. Nothing asks for a credit card, a licence key or an
account.

---

## Before you start — read this one paragraph

If you copied this folder **from another computer**, delete the `.venv` folder
inside it before doing anything else (if it is there at all).

A virtual environment records the exact path of the Python that created it, so
it cannot be moved between machines. Leaving a foreign `.venv` in place is the
single most common reason "it worked on his laptop but not mine".

* **Windows:** delete the `.venv` folder in File Explorer.
* **macOS / Linux:** `rm -rf .venv`

You can safely keep `db.sqlite3` if it is present — the database file *is*
portable, and keeping it preserves any complaints already in the system. If it
is missing, the steps below create it for you.

---

## Step 1 — Install Python (once per machine)

Check whether it is already installed. Open a terminal and run:

```
python --version
```

* **Windows:** press <kbd>Win</kbd>+<kbd>R</kbd>, type `cmd`, press Enter.
* **macOS:** open **Terminal** (Cmd+Space, type "Terminal").
* **Linux:** open your terminal.

**If it prints `Python 3.11` or higher — skip to Step 2.**

If it prints something lower, prints nothing, or says "not recognized", install
it:

| System | How |
|---|---|
| **Windows** | Download from <https://www.python.org/downloads/> and run the installer. **On the first screen, tick "Add python.exe to PATH"** before clicking Install. This checkbox is easy to miss and skipping it causes most "python is not recognized" errors. |
| **macOS** | `brew install python@3.13`, or download from <https://www.python.org/downloads/> |
| **Ubuntu / Debian** | `sudo apt update && sudo apt install python3 python3-venv python3-pip` |
| **Fedora** | `sudo dnf install python3 python3-pip` |

After installing on Windows, **close the terminal and open a new one** — the
PATH change only applies to new terminals.

---

## Step 2 — Start the project

### Method A — one click (recommended)

**Windows**

Open the project folder in File Explorer and **double-click `run.bat`**.

**macOS / Linux**

Open a terminal in the project folder and run:

```bash
chmod +x run.sh    # only needed the first time
./run.sh
```

That is the whole thing. You will see:

```
 [1/5] Using Python 3.13.5
 [2/5] Creating the virtual environment (one-off, ~10 seconds) ...
 [3/5] Installing dependencies (one-off, needs internet, ~2 minutes) ...
 [4/5] Creating the database and loading demo data ...
 [5/5] Starting the server ...

 ==========================================================
  Open:  http://127.0.0.1:8000/
 ==========================================================
```

Your browser opens automatically. **Leave that black window open** — closing it
stops the server.

The first run takes about 2–3 minutes because it downloads the libraries. Every
run after that starts in a couple of seconds.

### Method B — manual commands

Use this if you prefer to see each step, or if the launcher fails.

Open a terminal **inside the project folder** (the one containing `manage.py`).

> **Tip — opening a terminal in the right folder.**
> Windows: type `cmd` into the File Explorer address bar and press Enter.
> macOS: right-click the folder → Services → New Terminal at Folder.
> Linux: right-click inside the folder → Open in Terminal.

**Windows (Command Prompt):**

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py seed_demo_data
.venv\Scripts\python.exe manage.py runserver
```

**macOS / Linux:**

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_demo_data
.venv/bin/python manage.py runserver
```

What each command does:

| Command | Purpose |
|---|---|
| `python -m venv .venv` | Creates a private folder for this project's libraries so it cannot clash with anything else on your computer |
| `pip install -r requirements.txt` | Downloads Django and the other free libraries |
| `manage.py migrate` | Builds the database tables |
| `manage.py seed_demo_data` | Loads 3 departments, 8 users and 15 sample complaints |
| `manage.py runserver` | Starts the web server |

Then open **<http://127.0.0.1:8000/>** in your browser yourself.

---

## Step 3 — Sign in

Password for **every** demo account: **`Portal@2026`**

| Role | Email | What you can do |
|---|---|---|
| **Principal / Admin** | `principal@mao.edu.pk` | See all complaints, manage users, unmask anonymous complaints, view analytics and the activity log |
| **HOD (Information Technology)** | `haseeb.azmat@mao.edu.pk` | See and manage only IT complaints |
| **HOD (Hostel)** | `nadia.iqbal@mao.edu.pk` | See and manage only Hostel complaints |
| **Student** | `abdul.wahab@student.mao.edu.pk` | Submit and track own complaints |
| **Student** | `mohsin.ali@student.mao.edu.pk` | Submit and track own complaints |

You may sign in with **either the email address or the ID** (e.g.
`BSIT-22-084600` for Abdul Wahab).

> **Change these passwords before any real use.** They exist only so the demo
> works out of the box.

### A 2-minute tour worth doing

1. Sign in as **`abdul.wahab@student.mao.edu.pk`** → **Submit Complaint** → tick
   **"Submit anonymously"** → submit.
2. Sign out, sign in as **`haseeb.azmat@mao.edu.pk`** (the IT HOD) → open that
   complaint. The complainant shows as **Anonymous**, and searching for
   "Abdul Wahab" returns nothing.
3. Sign out, sign in as **`principal@mao.edu.pk`** → open the same complaint →
   **Unmask identity** → give a reason. The name is revealed to you only.
4. Go to **Activity Log** — your unmasking is permanently recorded with the
   reason you typed.
5. Sign in as **`nadia.iqbal@mao.edu.pk`** (the Hostel HOD) — the IT complaint is
   not in her list, and opening it by URL gives **403 Access Denied**.

---

## Step 4 — Stop the server

Click the terminal window and press <kbd>Ctrl</kbd>+<kbd>C</kbd>. Closing the
window also works.

To start again later, double-click `run.bat` (or `./run.sh`). It will skip the
setup steps and start immediately.

---

## Running on a machine with no internet

The first run normally downloads the libraries. To avoid that entirely:

**On a computer that has internet**, inside the project folder:

```bash
pip download -r requirements.txt -d vendor
```

This creates a `vendor` folder of about 40 MB. Copy the **whole project folder,
including `vendor`**, to the offline machine and run `run.bat` / `run.sh` as
normal — it detects `vendor` and installs without any network access.

Two caveats: the downloaded files are specific to the operating system and
Python version, so download them on the same kind of machine you will run on.
And Python itself must still be installed on the offline machine.

---

## Letting other devices on the network use it

By default the portal is reachable only from the machine running it. To open it
to phones and other computers on the same Wi-Fi:

**1. Start it on all interfaces**

```
.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000
```
```bash
.venv/bin/python manage.py runserver 0.0.0.0:8000
```

**2. Find this machine's address**

* Windows: `ipconfig` → look for **IPv4 Address** (e.g. `192.168.0.107`)
* macOS / Linux: `ip addr` or `ifconfig`

**3. Allow it through the firewall (Windows only)**

Windows usually shows a prompt the first time — click **Allow access**. If no
prompt appears, open PowerShell **as Administrator** and run:

```powershell
New-NetFirewallRule -DisplayName "OCR Portal 8000" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow -Profile Private
```

**4. On the other device**, open `http://192.168.0.107:8000/` (substitute your
own address).

Both devices must be on the same network. This is intended for a classroom demo
or a college LAN — for a real internet-facing deployment follow the production
section of [README.md](README.md).

---

## Troubleshooting

### "python is not recognized as an internal or external command"

Python is not installed, or the **"Add python.exe to PATH"** checkbox was missed
during installation. Reinstall from <https://www.python.org/downloads/> with
that box ticked, then **open a new terminal**.

If Windows opens the Microsoft Store instead of running Python, that is
Windows' placeholder. Either install from python.org, or disable the stub under
**Settings → Apps → Advanced app settings → App execution aliases** by turning
off both `python.exe` entries.

### "Error: That port is already in use."

Something else is on port 8000 — very often a copy of this server you forgot to
close. Either use a different port:

```
.venv\Scripts\python.exe manage.py runserver 8001
```

(then browse to `http://127.0.0.1:8001/`), or close the old one:

* Windows: `taskkill /F /IM python.exe`
* macOS / Linux: `pkill -f runserver`

### "cannot be loaded because running scripts is disabled on this system"

PowerShell blocks scripts by default. You do **not** need to change that — use
`run.bat`, or use Command Prompt (`cmd`) instead of PowerShell. If you would
rather allow it, in PowerShell as Administrator:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### The dependency install fails or times out

Almost always the network. Check your connection and run it again — pip resumes
from what it already downloaded. On a slow or filtered college connection, use
the offline `vendor` method above.

### "ModuleNotFoundError: No module named 'django'"

You are running the system Python rather than the project's. Always use the one
inside `.venv`:

```
.venv\Scripts\python.exe manage.py runserver     ← correct
python manage.py runserver                        ← wrong
```

Or simply use `run.bat` / `run.sh`, which always pick the right one.

### It worked on another computer but not this one

You copied the `.venv` folder across. Delete it and run `run.bat` / `run.sh`
again — see the note at the top of this guide.

### I want to wipe everything and start fresh

Delete `db.sqlite3` and run the launcher again. It rebuilds the database and
reloads the demo data. All complaints and accounts are reset.

To reload only the sample complaints without touching the accounts:

```
.venv\Scripts\python.exe manage.py seed_demo_data --flush-complaints
```

### Where do the notification emails go?

In development they are **printed into the terminal window** running the server,
not actually sent — so you can see the whole email without configuring anything.
Submit a complaint and look at the terminal.

To send real email, follow the production section of [README.md](README.md); it
uses a free Gmail App Password.

---

## Checking everything works

To run the automated test suite (284 tests):

```
.venv\Scripts\python.exe manage.py test tests --settings=config.settings.test
```
```bash
.venv/bin/python manage.py test tests --settings=config.settings.test
```

Expected output ends with:

```
Ran 284 tests in ...s

OK
```

---

## Quick reference card

| Task | Windows | macOS / Linux |
|---|---|---|
| **Start everything** | double-click `run.bat` | `./run.sh` |
| Stop the server | Ctrl+C | Ctrl+C |
| Open the portal | <http://127.0.0.1:8000/> | <http://127.0.0.1:8000/> |
| Any account's password | `Portal@2026` | `Portal@2026` |
| Admin account | `principal@mao.edu.pk` | `principal@mao.edu.pk` |
| Run the tests | `.venv\Scripts\python.exe manage.py test tests --settings=config.settings.test` | `.venv/bin/python manage.py test tests --settings=config.settings.test` |
| Reset the database | delete `db.sqlite3`, run again | `rm db.sqlite3`, run again |
| Share on the LAN | `manage.py runserver 0.0.0.0:8000` | `manage.py runserver 0.0.0.0:8000` |

For architecture, requirements traceability, Docker and production deployment,
see [README.md](README.md).
