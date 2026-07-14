@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo ============================================================
echo  SnowRunner Telemetry API — Fase 1 comprobar
echo ============================================================
echo.

set "PY=python"
if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
    echo [INFO] Usando venv: .venv
) else (
    echo [INFO] Sin .venv — ejecuta: python -m venv .venv
    echo [INFO] Luego: .venv\Scripts\pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -e ".[dev]"
)

echo.
echo --- Python ---
"%PY%" --version
if errorlevel 1 (
    echo [FALLO] Python no encontrado
    exit /b 1
)

echo.
echo --- Instalar dependencias ---
"%PY%" -c "import fastapi, pytest" >nul 2>&1
if errorlevel 1 (
    "%PY%" -m pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -e ".[dev]" -q
    if errorlevel 1 (
        echo [FALLO] pip install
        exit /b 1
    )
) else (
    echo [OK] dependencias ya instaladas
)

echo.
echo --- Tests pytest ---
"%PY%" -m pytest -q
if errorlevel 1 (
    echo [FALLO] pytest
    exit /b 1
)
echo [OK] tests unitarios

echo.
echo --- Comprobacion CSV + API ---
"%PY%" -m snowrunner_telemetry_api.fase1_check
set "CHK=%ERRORLEVEL%"
if not "%CHK%"=="0" exit /b %CHK%

echo.
echo --- Opcional: servidor en vivo (5 s) ---
set "PORT=8765"
if defined SNOWRUNNER_API_PORT set "PORT=%SNOWRUNNER_API_PORT%"

netstat -ano | findstr ":%PORT% " | findstr LISTENING >nul 2>&1
if not errorlevel 1 (
    echo [INFO] Puerto %PORT% ya en uso - probando API en vivo existente
    goto :live_http
)

echo [INFO] Arrancando API en http://127.0.0.1:%PORT% ...
start "snowrunner-api-fase1" /B "%PY%" -m uvicorn snowrunner_telemetry_api.main:app --host 127.0.0.1 --port %PORT% >nul 2>&1
timeout /t 2 /nobreak >nul
set "KILL_AFTER=1"

:live_http
powershell -NoProfile -Command ^
  "try { $r = Invoke-RestMethod 'http://127.0.0.1:%PORT%/' -TimeoutSec 5; if (-not $r.name) { exit 1 }; Write-Host ('[OK] GET / name=' + $r.name); $h = Invoke-RestMethod 'http://127.0.0.1:%PORT%/v1/health' -TimeoutSec 5; if ($h.status -ne 'ok') { exit 1 }; $s = Invoke-RestMethod 'http://127.0.0.1:%PORT%/v1/sample' -TimeoutSec 5; Write-Host ('[OK] HTTP vivo vehicle=' + $s.vehicle_id + ' speed=' + $s.speed_kmh) } catch { Write-Host '[FALLO] HTTP vivo:' $_.Exception.Message; exit 1 }"
set "HTTP=%ERRORLEVEL%"

if defined KILL_AFTER (
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT% " ^| findstr LISTENING') do (
        taskkill /PID %%a /F >nul 2>&1
    )
)

if not "%HTTP%"=="0" exit /b %HTTP%

:done
echo.
echo ============================================================
echo  Fase 1 lista — para usar: python -m snowrunner_telemetry_api
echo ============================================================
echo.
exit /b 0
