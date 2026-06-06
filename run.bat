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

if /i "%~1"=="scan" goto do_scan
if /i "%~1"=="speak" goto do_speak
goto do_listen

:do_scan
echo === BLE scan (10 sec) ===
"%PYTHON%" scan.py
goto done

:do_speak
echo === Listen forever (with speech). Stop: Ctrl+C ===
"%PYTHON%" bind_init.py --listen-forever --speak
goto done

:do_listen
echo === Listen forever. Stop: Ctrl+C ===
echo For speech use: run_speak.bat
echo.
"%PYTHON%" bind_init.py --listen-forever
goto done

:done
set EXITCODE=%ERRORLEVEL%
if "%EXITCODE%"=="0" exit /b 0
if "%EXITCODE%"=="130" exit /b 0
if "%EXITCODE%"=="-1073741510" exit /b 0
echo.
echo ERROR: program exited with code %EXITCODE%
pause
exit /b %EXITCODE%
