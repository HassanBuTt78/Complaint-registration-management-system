#!/usr/bin/env bash
# ===========================================================================
#  Online Complaint Registration & Management System - one-click launcher
#
#  Usage:  ./run.sh        (macOS / Linux; make it executable first:
#                           chmod +x run.sh)
#
#  It will find Python 3.11+, create the virtual environment, install the
#  dependencies, create and seed the database, then start the server.
#  Internet is needed only the FIRST time, to download the dependencies.
# ===========================================================================
set -euo pipefail
cd "$(dirname "$0")"

echo
echo " =========================================================="
echo "  Online Complaint Registration & Management System"
echo "  Govt. M.A.O Graduate College, Lahore"
echo " =========================================================="
echo

# --- 1. Locate Python -------------------------------------------------------
PYTHON=""
for candidate in python3.13 python3.12 python3.11 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' 2>/dev/null; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo " [ERROR] Python 3.11 or newer was not found."
    echo
    echo " Install it free:"
    echo "   Ubuntu/Debian : sudo apt install python3 python3-venv"
    echo "   macOS         : brew install python@3.13"
    echo "   or download   : https://www.python.org/downloads/"
    exit 1
fi

echo " [1/5] Using $("$PYTHON" --version)"

# --- 2. Virtual environment -------------------------------------------------
if [ ! -x ".venv/bin/python" ]; then
    echo " [2/5] Creating the virtual environment (one-off, ~10 seconds) ..."
    "$PYTHON" -m venv .venv
else
    echo " [2/5] Virtual environment found."
fi
VPY=".venv/bin/python"

# --- 3. Dependencies --------------------------------------------------------
if ! "$VPY" -c "import django, environ, axes, whitenoise, reportlab, pymysql, PIL" >/dev/null 2>&1; then
    echo " [3/5] Installing dependencies (one-off, needs internet, ~2 minutes) ..."
    "$VPY" -m pip install --upgrade pip --quiet
    if [ -d "vendor" ]; then
        echo "       Offline wheels found - installing without internet."
        "$VPY" -m pip install --no-index --find-links vendor -r requirements.txt --quiet
    else
        "$VPY" -m pip install -r requirements.txt --quiet
    fi
else
    echo " [3/5] Dependencies already installed."
fi

# --- 4. Database ------------------------------------------------------------
if [ ! -f "db.sqlite3" ]; then
    echo " [4/5] Creating the database and loading demo data ..."
    "$VPY" manage.py migrate --noinput
    "$VPY" manage.py seed_demo_data
else
    echo " [4/5] Database found - applying any new migrations ..."
    "$VPY" manage.py migrate --noinput
fi

# --- 5. Run -----------------------------------------------------------------
echo
echo " [5/5] Starting the server ..."
echo
echo " =========================================================="
echo "  Open:  http://127.0.0.1:8000/"
echo
echo "  Sign in with any of these (password: Portal@2026)"
echo "    Principal : principal@mao.edu.pk"
echo "    HOD       : haseeb.azmat@mao.edu.pk"
echo "    Student   : abdul.wahab@student.mao.edu.pk"
echo
echo "  Press CTRL+C to stop the server."
echo " =========================================================="
echo

if command -v xdg-open >/dev/null 2>&1; then
    (sleep 2 && xdg-open http://127.0.0.1:8000/ >/dev/null 2>&1) &
elif command -v open >/dev/null 2>&1; then
    (sleep 2 && open http://127.0.0.1:8000/ >/dev/null 2>&1) &
fi

exec "$VPY" manage.py runserver 127.0.0.1:8000
