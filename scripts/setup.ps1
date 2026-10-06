# Vehicle Service CRM - one-time local setup without Docker (built by Sahil Thakur)
# Usage (PowerShell, from the repo root):  .\scripts\setup.ps1          [-NoSeed] [-Fresh]
param(
    [switch]$NoSeed,   # skip demo data
    [switch]$Fresh     # delete backend\dev.sqlite3 and start from an empty database
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$venvPython = Join-Path $backend ".venv\Scripts\python.exe"

function Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }

# --- Python 3.12 virtualenv ---------------------------------------------------
Step "Python environment"
if (-not (Test-Path $venvPython)) {
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        uv venv --python 3.12 (Join-Path $backend ".venv")
    } elseif (Get-Command py -ErrorAction SilentlyContinue) {
        py -3.12 -m venv (Join-Path $backend ".venv")
    } else {
        throw "Python 3.12 not found. Install it from python.org (or install 'uv'), then re-run this script."
    }
}
if (Get-Command uv -ErrorAction SilentlyContinue) {
    uv pip install --python $venvPython -r (Join-Path $backend "requirements\dev.txt")
} else {
    & $venvPython -m pip install --upgrade pip
    & $venvPython -m pip install -r (Join-Path $backend "requirements\dev.txt")
}

# --- Database -----------------------------------------------------------------
Step "Database (SQLite: backend\dev.sqlite3)"
Push-Location $backend
try {
    $env:DJANGO_SETTINGS_MODULE = "config.settings.dev"
    Remove-Item Env:DATABASE_URL, Env:REDIS_URL, Env:CACHE_URL -ErrorAction SilentlyContinue
    if ($Fresh -and (Test-Path "dev.sqlite3")) {
        Remove-Item "dev.sqlite3*" -Force
        Write-Host "Removed old dev.sqlite3"
    }
    & $venvPython manage.py migrate --noinput
    if (-not $NoSeed) {
        Step "Demo data"
        & $venvPython manage.py seed_demo_data
    }
} finally {
    Pop-Location
}

# --- Frontend -------------------------------------------------------------------
Step "Frontend packages"
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "Node.js 20.19+ not found. Install it from nodejs.org, then re-run this script."
}
Push-Location $frontend
try { npm install --no-audit --no-fund } finally { Pop-Location }

Write-Host "`nSetup complete. Start everything with:  .\scripts\start.ps1   (or double-click start.bat)" -ForegroundColor Green
Write-Host "Built by Sahil Thakur" -ForegroundColor DarkGray
