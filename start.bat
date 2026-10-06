@echo off
REM Vehicle Service CRM - start API, scheduler and web app without Docker (built by Sahil Thakur)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1" %*
