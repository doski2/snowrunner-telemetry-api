@echo off
cd /d "%~dp0"
echo Grabando telemetria de juego normal (Ctrl+C para parar). Datos en data\sessions
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe -m snowrunner_telemetry_api.autorecord %*
) else (
    python -m snowrunner_telemetry_api.autorecord %*
)
