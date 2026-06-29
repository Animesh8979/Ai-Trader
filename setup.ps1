# =============================================================================
#  Godmode Trading Agent — one-time setup (Windows PowerShell)
#  Creates a private virtual environment, installs the project, runs the wizard.
#  If a script is blocked, run once:  Set-ExecutionPolicy -Scope Process -Bypass
# =============================================================================
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

Write-Host "`n=== Godmode Trading Agent — setup ===`n" -ForegroundColor Cyan

# 1) Find a Python 3.10+ launcher.
$pythonCmd = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonCmd = "py -3"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonCmd = "python"
} else {
    Write-Host "Python was not found. Install Python 3.10+ from https://www.python.org/downloads/ and re-run." -ForegroundColor Red
    exit 1
}
Write-Host "Using Python launcher: $pythonCmd"

# 2) Create the virtual environment (.venv) if missing.
if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    Write-Host "Creating virtual environment in .venv ..." -ForegroundColor Yellow
    Invoke-Expression "$pythonCmd -m venv .venv"
} else {
    Write-Host ".venv already exists — reusing it."
}
$py = ".\.venv\Scripts\python.exe"

# 3) Install the project (editable) + dev extras.
Write-Host "`nInstalling dependencies (this can take a few minutes)..." -ForegroundColor Yellow
& $py -m pip install --upgrade pip
& $py -m pip install -e ".[dev]"

# 4) Launch the setup wizard.
Write-Host "`nLaunching the setup wizard..." -ForegroundColor Cyan
& $py -m godmode.cli setup

Write-Host "`nSetup complete. Useful next commands:" -ForegroundColor Green
Write-Host "    ./run.ps1 smoke      # test that everything works"
Write-Host "    ./run.ps1 status     # see current status"
Write-Host "    ./run.ps1 stop       # emergency halt"
