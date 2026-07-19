# SnowRunner Telemetry Agent (C#)

Agente nativo Windows — lectura de memoria Havok. Proceso aparte que empujará muestras a la API (`POST /internal/ingest` en Fase 2.4).

**Estado:** Fases **2.0** + **2.1** cerradas — ver [docs/ROADMAP.md](../docs/ROADMAP.md#fase-2--agente-nativo-c-memoria).

## Qué cubre cada subfase

| Subfase | Entregable | Comprobar |
|---------|------------|-----------|
| **2.0** | Proyecto .NET 8, P/Invoke `kernel32`/`psapi`, `OpenProcess` + `ReadProcessMemory`, base del módulo | `dotnet build` |
| **2.1** | Spike `read_active_sample`: `vehicle_id`, `speed_kmh`, `throttle_input` (memoria + volante) | `.\fase2_comprobar.bat` o juego abierto + `.\run_agent.bat` |

Adelanto de **2.3** (ya en el repo, no cerrado como tarea): carga de `offsets_referencia.json` y `ThrottleResolver` portado desde Python.

Extensión práctica en **2.1**: lectura de pedal por **WinMM** (`joyGetPosEx`, eje RZ) cuando DirectInput está bloqueado con SnowRunner abierto (VelocityOne).

## Requisitos

- Windows 10/11 x64
- [.NET 8 SDK](https://dotnet.microsoft.com/download/dotnet/8.0)
- SnowRunner en ejecución con un vehículo cargado en mapa (prueba completa 2.1)
- `data/offsets_referencia.json` (copia de `snowrunner real/cheat_engine/`)

## Compilar y probar

```powershell
cd agent
dotnet build
dotnet run
```

Con el juego abierto deberías ver JSON con `vehicle_id`, `speed_kmh`, `throttle_input` / `throttle_motor`:

```json
{
  "probe_ok": true,
  "chain": "TRUCK_CONTROL",
  "vehicle_id": "s_fleetstar_f2070a",
  "speed_kmh": 0.0,
  "throttle_input": "0.152",
  "throttle_motor": "1.000",
  "throttle_input_src": "winmm",
  "physical_input_axis": "Rz"
}
```

`throttle_input` = pedal (hardware o memoria). `throttle_motor` = aplicación del motor en Havok (a menudo alto en reposo; no es el pedal).

Checklist automatizado (build + offsets + WinMM; probe en vivo si el juego está abierto):

```powershell
cd ..
.\fase2_comprobar.bat
```

Modo continuo (poll cada 500 ms):

```powershell
dotnet run -- --loop
dotnet run -- --loop --interval=1000
```

### Volante / mando (auto)

Prioridad: **WinMM** → **WinGame HID** → **DirectInput** → **XInput**. Sin flags.

Al arrancar: `[OK] Volante winmm (Eje RZ) detectado — Controla. Microsoft PC-joystick (joy0)`

| Flag | Efecto |
|------|--------|
| `--memory-only` | Ignorar volante/mando; solo Havok |
| `--list-devices` | Lista WinMM/DirectInput/XInput (diagnóstico) |
| `--watch-input` | Monitor en vivo del eje de gas (Ctrl+C sale) |
| `--watch-input --interval=100` | Poll más rápido (ms) |
| `--fuel-diff --wait=5000` | Diff combustible tras N ms (default 5000) |
| `--physical-only` | Forzar pedal solo desde hardware |
| `--xinput-index=N` | Preferir slot XInput 0–3 |

**VelocityOne + SnowRunner:** pedal = **Eje RZ**. Con el juego abierto, DirectInput suele estar bloqueado; WinMM lee vía `joy0`.

Códigos de salida: `0` OK · `1` juego no en ejecución · `2` offsets/memoria · `3` probe fallido (cadena Havok o muestra incompleta).

### Depurar en VS Code / Cursor

Abre la carpeta `agent/` en el workspace y F5 — configs en `agent/.vscode/launch.json` (lanzan `dotnet run`).

Para **breakpoints C#** instala **C# Dev Kit** y usa `type: "coreclr"` con `program` apuntando al `.dll` en `bin/Debug/net8.0-windows10.0.19041.0/`.

## Publicar (win-x64)

```powershell
dotnet publish -c Release -r win-x64 --self-contained false
# bin\Release\net8.0-windows10.0.19041.0\win-x64\publish\snowrunner-telemetry-agent.exe
```

## Estructura

| Carpeta / archivo | Rol | Fase |
|-------------------|-----|------|
| `Native/Kernel32.cs`, `Native/Psapi.cs` | P/Invoke Win32 | 2.0 |
| `Memory/GameProcess.cs` | Handle RAII al proceso | 2.0 |
| `Memory/ProcessMemoryReader.cs` | Lecturas tipadas + base del módulo | 2.0 |
| `Platform/SnowRunnerLocator.cs` | Buscar PID por nombre | 2.0 |
| `Config/OffsetsReference.cs` | Carga `offsets_referencia.json` | 2.1 (adelanto 2.3) |
| `Havok/ActiveSampleReader.cs` | Spike `read_active_sample` | 2.1 |
| `Program.Session.cs` | `GameSession` — offsets + proceso + módulo | 2.1 |
| `Program.FuelScan.cs`, `Program.FuelDiff.cs` | Diagnóstico combustible | 2.1 (investigación) |
| `Havok/ThrottleResolver.cs` | Resolución throttle en memoria | 2.1 (adelanto 2.3) |
| `Input/WinMmJoystickReader.cs` | Pedal vía `joyGetPosEx` (Eje RZ) | 2.1 |
| `Input/PhysicalInputReader.cs` | Orquesta backends físicos | 2.1 |

## Variables de entorno (Fase 2.3+)

| Variable | Default |
|----------|---------|
| `SNOWRUNNER_OFFSETS_PATH` | `data/offsets_referencia.json` junto al exe |
| `SNOWRUNNER_AGENT_INGEST_URL` | `http://127.0.0.1:8765/internal/ingest` |
| `SNOWRUNNER_AGENT_INTERVAL_MS` | `100` |

## Referencia Python

Port desde `snowrunner real/cheat_engine/memoria_havok.py` y `offsets_referencia.json`.
