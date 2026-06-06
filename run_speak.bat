@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

set "PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    echo ERROR: .venv not found. Run setup.bat first.
    pause
    exit /b 1
)

"%PYTHON%" -c "import pyttsx3" 2>nul
if errorlevel 1 (
    echo ERROR: pyttsx3 not installed. Run setup.bat again.
    pause
    exit /b 1
)

echo === Speech test (you should hear Japanese) ===
"%PYTHON%" -c "import sys; sys.path.insert(0,'.'); from speech import speak_test_message; sys.exit(0 if speak_test_message() else 1)"
if errorlevel 1 (
    echo.
    echo WARNING: Speech test failed.
    echo Install Japanese speech in Windows Settings - Time ^& Language - Speech.
    echo.
    pause
    exit /b 1
)

echo.
echo === Listen with speech. Stop: Ctrl+C ===
echo Speed is spoken when you shoot BB.
echo.
"%PYTHON%" bind_init.py --listen-forever --speak
set EXITCODE=%ERRORLEVEL%
if not "%EXITCODE%"=="0" pause
exit /b %EXITCODE%
