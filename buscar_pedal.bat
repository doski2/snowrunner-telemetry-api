@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "MAIN=%~dp0..\snowrunner real"
if not exist "%MAIN%\banco_auto_pedal.bat" (
    set "MAIN=%USERPROFILE%\snowrunner real"
)
if not exist "%MAIN%\banco_auto_pedal.bat" (
    echo [FALLO] No encuentro snowrunner real en:
    echo   %~dp0..\snowrunner real
    exit /b 1
)

echo.
echo ============================================================
echo  Buscar pedal Fleetstar / cualquier camion
echo ============================================================
echo.
echo  1. Barrido 5s — alterna gas SUELTO y FONDO en el juego
echo  2. Aplica el mejor candidato a offsets_referencia.json
echo  3. Copia JSON al agente C#
echo.

cd /d "%MAIN%"
call banco_auto_pedal.bat --sweep-duration 8
if errorlevel 1 exit /b 1

echo.
echo --- Aplicar candidato #1 ---
python cheat_engine/calibrar_drive.py --from-sweep --apply
if errorlevel 1 exit /b 1

echo.
echo --- Copiar offsets al agente ---
copy /Y "cheat_engine\offsets_referencia.json" "%~dp0agent\data\offsets_referencia.json"
if errorlevel 1 exit /b 1

echo.
echo --- Probe Python ---
python grabar_ce.py --probe

echo.
echo --- Agente C# (una muestra) ---
cd /d "%~dp0"
call run_agent.bat

echo.
echo Listo. Para monitor en vivo: run_agent.bat --loop
exit /b 0
