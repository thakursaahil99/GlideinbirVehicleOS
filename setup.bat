@echo off
REM Glideinbir - one-time setup without Docker (built by Sahil Thakur)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup.ps1" %*
pause
