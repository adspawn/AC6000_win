@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set PYTHONUTF8=1
set "PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    echo ERROR: Run setup.bat first.
    pause
    exit /b 1
)

echo Testing TTS only...
"%PYTHON%" -c "import sys; sys.path.insert(0,'.'); from speech import speak_test_message; sys.exit(0 if speak_test_message() else 1)"
if errorlevel 1 (
    echo FAILED
    pause
    exit /b 1
)
echo OK
pause
exit /b 0
