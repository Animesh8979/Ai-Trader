@echo off
rem =============================================================================
rem  Godmode Trading Agent — launcher (Windows Command Prompt)
rem  Forwards all arguments to the godmode CLI inside the project's virtual env.
rem  If no arguments are provided, it defaults to launching the web dashboard.
rem  Examples:
rem     run.bat
rem     run.bat status
rem     run.bat stop
rem     run.bat resume
rem =============================================================================

setlocal enabledelayedexpansion

cd /d "%~dp0"

set "PYTHON_EXE=.\.venv\Scripts\python.exe"

if not exist "!PYTHON_EXE!" (
    echo [ERROR] No virtual environment found. Run setup.ps1 in PowerShell first.
    echo.
    echo Press any key to exit...
    pause >nul
    exit /b 1
)

if "%~1"=="" (
    echo [SYS] Launching Godmode Trading Terminal Dashboard...
    echo [SYS] Please wait, starting uvicorn server...
    echo.
    "!PYTHON_EXE!" -m godmode.cli dashboard
    echo.
    echo [SYS] Dashboard server stopped.
    echo Press any key to exit...
    pause >nul
    exit /b 0
)

"!PYTHON_EXE!" -m godmode.cli %*
exit /b %ERRORLEVEL%
