@echo off
title XLedgerMate Dashboard Tunnel
cd /d "%~dp0"

if exist "%~dp0launcher\XLedgerMate-Dashboard.exe" (
    start "" "%~dp0launcher\XLedgerMate-Dashboard.exe"
    exit /b 0
)

echo Building launcher exe (one-time)...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launcher\build_exe.ps1"
if exist "%~dp0launcher\XLedgerMate-Dashboard.exe" (
    start "" "%~dp0launcher\XLedgerMate-Dashboard.exe"
    exit /b 0
)

echo.
echo Could not build .exe — using PowerShell fallback.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_tunnel.ps1"
pause