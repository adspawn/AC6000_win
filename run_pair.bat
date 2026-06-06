@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set "PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    echo ERROR: Run setup.bat first.
    pause
    exit /b 1
)
echo === Checking stale bind_init.py ===
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_stale_bind.ps1"
echo.
echo === Listen with Windows pairing (--pair) ===
"%PYTHON%" bind_init.py --listen-forever --pair
if errorlevel 1 pause
exit /b %ERRORLEVEL%
