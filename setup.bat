@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo === AC6000BT Setup ===
echo.

set "PYEXE="
where py >nul 2>&1
if not errorlevel 1 set "PYEXE=py -3"

if not defined PYEXE (
    where python >nul 2>&1
    if not errorlevel 1 set "PYEXE=python"
)

if not defined PYEXE (
    if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
        set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    )
)

if not defined PYEXE (
    echo ERROR: Python not found. Install Python 3.11+ from https://www.python.org/
    echo Enable "Add python.exe to PATH" during install.
    pause
    exit /b 1
)

echo Using: %PYEXE%

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    %PYEXE% -m venv .venv
    if errorlevel 1 (
        echo ERROR: Failed to create venv.
        pause
        exit /b 1
    )
)

echo Installing packages...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: pip install failed.
    pause
    exit /b 1
)

echo.
echo Setup complete. Run run.bat to start.
pause
exit /b 0
