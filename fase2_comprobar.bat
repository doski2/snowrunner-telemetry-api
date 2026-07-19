@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo ============================================================
echo  SnowRunner Telemetry API — Fase 2.0 / 2.1 comprobar
echo ============================================================
echo.

set "FAIL=0"
set "AGENT_PROJ=agent\SnowrunnerTelemetryAgent.csproj"
set "OUT=%TEMP%\snowrunner_agent_probe.json"

echo --- .NET SDK ---
dotnet --version >nul 2>&1
if errorlevel 1 (
    echo [FALLO] dotnet no encontrado — instala .NET 8 SDK
    exit /b 1
)
for /f "delims=" %%v in ('dotnet --version') do echo [OK] dotnet %%v

echo.
echo --- Build agente ---
dotnet build "%AGENT_PROJ%" -v q
if errorlevel 1 (
    echo [FALLO] dotnet build agent
    exit /b 1
)
echo [OK] agent compila sin errores

echo.
echo --- offsets_referencia.json ---
if not exist "agent\data\offsets_referencia.json" (
    echo [FALLO] Falta agent\data\offsets_referencia.json
    echo         Copia desde snowrunner real\cheat_engine\
    set "FAIL=1"
) else (
    echo [OK] agent\data\offsets_referencia.json presente
)

echo.
echo --- WinMM / dispositivos ---
dotnet run --project "%AGENT_PROJ%" -v q -- --list-devices >nul 2>&1
if errorlevel 1 (
    echo [FALLO] --list-devices
    set "FAIL=1"
) else (
    echo [OK] --list-devices
)

echo.
set "GAME_RUNNING=0"
tasklist /FI "IMAGENAME eq SnowRunner.exe" 2>nul | find /I "SnowRunner.exe" >nul
if not errorlevel 1 set "GAME_RUNNING=1"

if "%GAME_RUNNING%"=="0" (
    echo --- Agente sin juego ^(esperado: exit 1^) ---
    dotnet run --project "%AGENT_PROJ%" -v q >nul 2>&1
    if errorlevel 1 (
        echo [OK] exit 1 — SnowRunner no en ejecucion
    ) else (
        echo [FALLO] exit 0 sin juego — esperado 1
        set "FAIL=1"
    )
    goto :summary
)

echo --- Probe en vivo ^(SnowRunner detectado^) ---
dotnet run --project "%AGENT_PROJ%" -v q > "%OUT%" 2>&1
set "PROBE_EXIT=%ERRORLEVEL%"

findstr /C:"\"probe_ok\": true" "%OUT%" >nul
if errorlevel 1 (
    echo [FALLO] probe_ok no es true — revisa offsets o vehiculo en mapa
    echo         Ultimas lineas:
    powershell -NoProfile -Command "Get-Content -Tail 8 '%OUT%'"
    set "FAIL=1"
) else (
    echo [OK] probe_ok=true
)

findstr /C:"vehicle_id" "%OUT%" | findstr /C:"s_" >nul
if errorlevel 1 (
    echo [FALLO] vehicle_id ausente o no empieza por s_
    set "FAIL=1"
) else (
    echo [OK] vehicle_id tipo s_* presente
)

if not "%PROBE_EXIT%"=="0" (
    echo [AVISO] exit code %PROBE_EXIT% — probe_ok puede ser true con exit 3 si speed fuera de rango
)

:summary
echo.
echo ============================================================
if "%FAIL%"=="0" (
    echo  Fase 2.0/2.1 OK — siguiente: 2.2 port Havok batched
    echo  Uso: .\run_agent.bat --loop
) else (
    echo  Hay fallos — revisa arriba
)
echo ============================================================
echo.
exit /b %FAIL%
