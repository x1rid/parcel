# Launch a Parcel entry point with the project's virtualenv interpreter.
# Usage:
#   .\run.ps1                 # runs main.py
#   .\run.ps1 run_editor.py   # runs the editor entry point

param(
    [string]$Target = "main.py"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Host "Virtualenv not found at $Python" -ForegroundColor Red
    Write-Host "Create it with:"
    Write-Host "  py -3.13 -m venv .venv"
    Write-Host "  .\.venv\Scripts\python.exe -m pip install -r requirements.txt"
    exit 1
}

$Path = Join-Path $Root $Target
if (-not (Test-Path $Path)) {
    Write-Host "Entry point not found: $Path" -ForegroundColor Red
    exit 1
}

& $Python $Path
exit $LASTEXITCODE
