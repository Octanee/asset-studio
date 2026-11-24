@echo off
rem Asset Studio on Windows: asset-studio setup ^| start ^| stop ^| status ^| logs [service]
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\asset-studio.ps1" %*
exit /b %ERRORLEVEL%
