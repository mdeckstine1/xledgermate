@echo off
REM Double-click or run from cmd: starts engine + GUI via run.ps1
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1"
if errorlevel 1 pause
