# SnowRunner Telemetry Agent (C#)

Agente nativo Windows — lectura de memoria Havok. Proceso aparte que empujará muestras a la API (`POST /internal/ingest` en Fase 2.4).

**Estado:** Fase **2.0** — scaffold + P/Invoke `kernel32` / `psapi`.

## Requisitos

- Windows 10/11 x64
- [.NET 8 SDK](https://dotnet.microsoft.com/download/dotnet/8.0)
- SnowRunner en ejecución (para la prueba de humo)

## Compilar y probar (2.0)

```powershell
cd agent
dotnet build
dotnet run
```

Con el juego abierto deberías ver:

```
[OK] PID ...
[OK] Module base 0x...
[OK] ReadProcessMemory — cabecera MZ valida
```

Sin juego: sale con código `1` y mensaje informativo (no es error de build).

## Publicar (win-x64)

```powershell
dotnet publish -c Release -r win-x64 --self-contained false
# bin\Release\net8.0\win-x64\publish\snowrunner-telemetry-agent.exe
```

## Estructura

| Carpeta / archivo | Rol |
|-------------------|-----|
| `Native/Kernel32.cs` | `OpenProcess`, `ReadProcessMemory`, `VirtualQueryEx`, `CloseHandle` |
| `Native/Psapi.cs` | `EnumProcessModulesEx`, `GetModuleBaseNameW` |
| `Memory/GameProcess.cs` | Handle RAII al proceso |
| `Memory/ProcessMemoryReader.cs` | Lecturas tipadas + base del módulo |
| `Platform/SnowRunnerLocator.cs` | Buscar PID por nombre |

## Variables de entorno (Fase 2.3+)

| Variable | Default |
|----------|---------|
| `SNOWRUNNER_OFFSETS_PATH` | `offsets_referencia.json` junto al exe |
| `SNOWRUNNER_AGENT_INGEST_URL` | `http://127.0.0.1:8765/internal/ingest` |
| `SNOWRUNNER_AGENT_INTERVAL_MS` | `100` |

## Referencia Python

Port desde `snowrunner real/cheat_engine/memoria_havok.py` y `offsets_referencia.json`.
