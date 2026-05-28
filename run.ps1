# XLedgerMate launcher - starts trading engine + GUI in separate terminals.
# Usage: .\run.ps1
# Or in Cursor: Terminal -> Run Task -> "XLedgerMate: Run All"

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

Write-Host "XLedgerMate - starting engine + GUI..." -ForegroundColor Cyan

# Trading engine (separate window)
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy", "Bypass",
    "-Command",
    "Set-Location '$repo'; Write-Host 'XLedgerMate Engine' -ForegroundColor Green; & '$py' main.py --mode engine"
)

Start-Sleep -Seconds 2

# Streamlit GUI (separate window)
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy", "Bypass",
    "-Command",
    "Set-Location '$repo'; Write-Host 'XLedgerMate GUI - http://localhost:8501' -ForegroundColor Green; & '$py' -m streamlit run gui/streamlit_gui.py --server.headless true --server.port 8501"
)

Write-Host ""
Write-Host "Launched:" -ForegroundColor Green
Write-Host "  Engine  -> separate PowerShell window"
Write-Host "  GUI     -> http://localhost:8501 (separate PowerShell window)"
Write-Host ""
Write-Host "Fill config/config.yaml with bot_account_address before live cycles."
