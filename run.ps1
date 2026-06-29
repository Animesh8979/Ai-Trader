# =============================================================================
#  Godmode Trading Agent — launcher (Windows PowerShell)
#  Forwards all arguments to the godmode CLI inside the project's virtual env.
#  Examples:
#     ./run.ps1 setup
#     ./run.ps1 smoke
#     ./run.ps1 status
#     ./run.ps1 stop
#     ./run.ps1 resume
# =============================================================================
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$py = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "No virtual environment found. Run ./setup.ps1 first." -ForegroundColor Yellow
    exit 1
}

& $py -m godmode.cli @args
exit $LASTEXITCODE
