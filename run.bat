@echo off
REM ===========================================================================
REM  Online Complaint Registration & Management System - one-click launcher
REM
REM  Double-click this file (or run `run.bat` in a terminal). It will:
REM    1. find a suitable Python (3.11 or newer)
REM    2. create the virtual environment, if missing
REM    3. install the dependencies, if missing
REM    4. create and seed the database, if missing
REM    5. start the server and open your browser
REM
REM  Everything it installs is free and open source. An internet connection is
REM  needed only the FIRST time, to download the dependencies.
REM ===========================================================================
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo  ==========================================================
echo   Online Complaint Registration ^& Management System
echo   Govt. M.A.O Graduate College, Lahore
echo  ==========================================================
echo.

REM --- 1. Locate Python -------------------------------------------------------
set "PYTHON="
for %%P in ("py -3.13" "py -3.12" "py -3.11" "py -3" "python" "python3") do (
    if not defined PYTHON (
        %%~P -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1
        if !errorlevel! equ 0 set "PYTHON=%%~P"
    )
)

if not defined PYTHON (
    echo  [ERROR] Python 3.11 or newer was not found on this computer.
    echo.
    echo  Install it free from https://www.python.org/downloads/
    echo  IMPORTANT: tick "Add Python to PATH" in the installer, then
    echo  close this window and run this file again.
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%V in ('%PYTHON% --version 2^>^&1') do set "PYVER=%%V"
echo  [1/5] Using Python !PYVER!

REM --- 2. Virtual environment -------------------------------------------------
if not exist ".venv\Scripts\python.exe" (
    echo  [2/5] Creating the virtual environment ^(one-off, ~10 seconds^) ...
    %PYTHON% -m venv .venv
    if !errorlevel! neq 0 (
        echo  [ERROR] Could not create the virtual environment.
        pause
        exit /b 1
    )
) else (
    echo  [2/5] Virtual environment found.
)
set "VPY=.venv\Scripts\python.exe"

REM --- 3. Dependencies --------------------------------------------------------
"%VPY%" -c "import django, environ, axes, whitenoise, reportlab, pymysql, PIL" >nul 2>&1
if !errorlevel! neq 0 (
    echo  [3/5] Installing dependencies ^(one-off, needs internet, ~2 minutes^) ...
    "%VPY%" -m pip install --upgrade pip --quiet
    if exist "vendor\" (
        echo        Offline wheels found - installing without internet.
        "%VPY%" -m pip install --no-index --find-links vendor -r requirements.txt --quiet
    ) else (
        "%VPY%" -m pip install -r requirements.txt --quiet
    )
    if !errorlevel! neq 0 (
        echo.
        echo  [ERROR] Dependency installation failed.
        echo  Check your internet connection and run this file again.
        pause
        exit /b 1
    )
) else (
    echo  [3/5] Dependencies already installed.
)

REM --- 4. Database ------------------------------------------------------------
if not exist "db.sqlite3" (
    echo  [4/5] Creating the database and loading demo data ...
    "%VPY%" manage.py migrate --noinput
    if !errorlevel! neq 0 (
        echo  [ERROR] Database setup failed.
        pause
        exit /b 1
    )
    "%VPY%" manage.py seed_demo_data
) else (
    echo  [4/5] Database found - applying any new migrations ...
    "%VPY%" manage.py migrate --noinput
)

REM --- 5. Run -----------------------------------------------------------------
echo.
echo  [5/5] Starting the server ...
echo.
echo  ==========================================================
echo   Open:  http://127.0.0.1:8000/
echo.
echo   Sign in with any of these ^(password: Portal@2026^)
echo     Principal : principal@mao.edu.pk
echo     HOD       : haseeb.azmat@mao.edu.pk
echo     Student   : abdul.wahab@student.mao.edu.pk
echo.
echo   Press CTRL+C in this window to stop the server.
echo  ==========================================================
echo.

start "" http://127.0.0.1:8000/
"%VPY%" manage.py runserver 127.0.0.1:8000

endlocal
