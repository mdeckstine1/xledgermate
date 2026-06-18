# XLedgerMate launcher — production WS engine + operator HUD.
# Usage: .\run.ps1
# Or in Cursor: Terminal -> Run Task -> "XLedgerMate: Run All"
# Legacy Streamlit lab: python main.py --mode gui  (http://localhost:8501)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "Virtual environment not found at .venv" -ForegroundColor Red
    Write-Host "Create it with:"
    Write-Host "  py -3.12 -m venv .venv"
    Write-Host "  .\.venv\Scripts\python.exe -m pip install -r requirements.txt"
    exit 1
}

if (-not (Test-Path "config\config.yaml")) {
    Write-Host "config/config.yaml not found." -ForegroundColor Yellow
    Write-Host "Copy the example and add your Bot Account credentials:"
    Write-Host "  copy config\config.example.yaml config\config.yaml"
    Write-Host ""
}

$repo = $PSScriptRoot -replace "'", "''"
$py = $python -replace "'", "''"

Write-Host "XLedgerMate - starting ws-engine + WS HUD..." -ForegroundColor Cyan

# Stop any leftover engine processes (avoids duplicate bots / stale pricing)
Write-Host "Stopping any existing engine processes..." -ForegroundColor Yellow
& $python -c "from gui.engine_control import stop_all_engines; c,m=stop_all_engines(); print(m)"
Start-Sleep -Seconds 1

# WS pure A-S engine (separate window)
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy", "Bypass",
    "-Command",
    "Set-Location '$repo'; Write-Host 'XLedgerMate WS Engine (production)' -ForegroundColor Green; & '$py' main.py --mode ws-engine"
)

Start-Sleep -Seconds 2

# Production HUD :8765 (separate window)
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy", "Bypass",
    "-Command",
    "Set-Location '$repo'; Write-Host 'XLedgerMate WS HUD - http://localhost:8765' -ForegroundColor Green; & '$py' main.py --mode ws-hud"
)

Write-Host ""
Write-Host "Launched:" -ForegroundColor Green
Write-Host "  ws-engine  -> separate PowerShell window (production MM)"
Write-Host "  WS HUD     -> http://localhost:8765 (separate PowerShell window)"
Write-Host "  Streamlit  -> legacy lab only: python main.py --mode gui"
Write-Host ""
Write-Host "Fill config/config.yaml with bot_account_address before live cycles."
