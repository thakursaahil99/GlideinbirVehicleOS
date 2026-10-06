# Vehicle Service CRM - start the whole app without Docker (built by Sahil Thakur)
# Opens three windows: Django API (:8000), the job scheduler, and the web app (:5173).
# Usage:  .\scripts\start.ps1   [-BackendPort 8000] [-FrontendPort 5173] [-NoScheduler]
param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173,
    [switch]$NoScheduler
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$venvPython = Join-Path $backend ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) { throw "Run .\scripts\setup.ps1 first." }

function PortBusy($port) {
    return [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}
if (PortBusy $BackendPort) { throw "Port $BackendPort is already in use (is the API already running?). Use -BackendPort 8001." }
if (PortBusy $FrontendPort) { throw "Port $FrontendPort is already in use. Use -FrontendPort 5174." }

# No DATABASE_URL / REDIS_URL -> SQLite + in-process cache + inline Celery tasks (see config/settings/dev.py).
$clean = "Remove-Item Env:DATABASE_URL, Env:REDIS_URL, Env:CACHE_URL -ErrorAction SilentlyContinue; `$env:DJANGO_SETTINGS_MODULE='config.settings.dev';"

Start-Process powershell -WorkingDirectory $backend -ArgumentList "-NoExit", "-Command",
    "`$host.UI.RawUI.WindowTitle='CRM API :$BackendPort'; $clean & '$venvPython' manage.py migrate --noinput; & '$venvPython' manage.py runserver 0.0.0.0:$BackendPort"

if (-not $NoScheduler) {
    Start-Process powershell -WorkingDirectory $backend -ArgumentList "-NoExit", "-Command",
        "`$host.UI.RawUI.WindowTitle='CRM scheduler'; $clean Start-Sleep -Seconds 4; & '$venvPython' manage.py run_scheduler"
}

Start-Process powershell -WorkingDirectory $frontend -ArgumentList "-NoExit", "-Command",
    "`$host.UI.RawUI.WindowTitle='CRM web :$FrontendPort'; `$env:VITE_PROXY_TARGET='http://localhost:$BackendPort'; npx vite --port $FrontendPort --strictPort"

Write-Host ""
Write-Host "Starting..." -ForegroundColor Cyan
Write-Host "  Web app   : http://localhost:$FrontendPort"
Write-Host "  API docs  : http://localhost:$BackendPort/api/v1/docs/"
Write-Host "  Admin     : http://localhost:$BackendPort/django-admin/"
Write-Host "  Demo login: superadmin@demo.local / Demo@12345  (also admin@speedy-auto-care.demo.local, customer01@demo.local)"
Write-Host "  E-mails print in the API window (console backend). Close the three windows to stop."
Write-Host "Built by Sahil Thakur" -ForegroundColor DarkGray
