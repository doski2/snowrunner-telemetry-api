@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe -m snowrunner_telemetry_api.dashboard %*
) else (
    python -m snowrunner_telemetry_api.dashboard %*
)
