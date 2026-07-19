@echo off
setlocal EnableExtensions
cd /d "%~dp0agent"
dotnet run --project SnowrunnerTelemetryAgent.csproj %*
exit /b %ERRORLEVEL%