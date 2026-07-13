# Arquitectura propuesta

Estado: **borrador** — alineado con [INVESTIGACION.md](INVESTIGACION.md).

## Vista general

                    ┌─────────────────────────────────────┐
                    │           SnowRunner.exe            │
                    │     (Havok, TRUCK_CONTROL, veh)     │
                    └──────────────────┬──────────────────┘
                                       │ ReadProcessMemory
                    ┌──────────────────▼──────────────────┐
                    │    Telemetry Agent (C# / .NET 8)    │
                    │         proceso Windows aparte      │
                    │                                     │
                    │  · OpenProcess / ReadProcessMemory  │
                    │  · VirtualQueryEx (cache regiones)  │
                    │  · read_active_sample + enrich      │
                    │  · throttle_resolver (portado)      │
                    │  · offsets_referencia.json          │
                    └──────────────────┬──────────────────┘
                                       │ POST /internal/ingest
                    ┌──────────────────▼──────────────────┐
                    │         API Server (FastAPI)        │
                    │  · normaliza Sample v1              │
                    │  · buffer circular (N muestras)     │
                    │  · persistencia sesiones (opcional) │
                    │  · OpenAPI /health /status /sample  │
                    └──────────────────┬──────────────────┘
                                       │ HTTP JSON
                    ┌──────────────────▼──────────────────┐
                    │         snowrunner real             │
                    │  · cliente import (futuro)          │
                    │  · comparar_telemetria / indexar    │
                    │  · sim / camiones / datos           │
                    └─────────────────────────────────────┘

## Componentes

### 1. Telemetry Agent (nativo C#)

| Atributo      | Valor                                                               |
|---------------|---------------------------------------------------------------------|
| SO            | Windows (obligatorio)                                               |
| Runtime       | .NET 8, publicación `win-x64` single-file opcional                  |
| Win32         | `OpenProcess`, `ReadProcessMemory`, `VirtualQueryEx`, `CloseHandle` |
| Origen lógica | Port desde `cheat_engine/memoria_havok.py` del principal            |
| Optimización  | Lecturas batched por struct (menos syscalls que `read_f32` suelto)  |
| Salida        | JSON `ce_sample_v1` → `POST /internal/ingest`                       |

**No expone HTTP al exterior.** Habla solo con el API server por:

- `POST http://127.0.0.1:8765/internal/ingest` — una muestra por request, o
- NDJSON por named pipe (spike opcional si POST es demasiado lento a >20 Hz)

**Fase 1:** no hay agente; la API lee CSV directamente (sin este componente).

### 2. API Server

| Responsabilidad  | Detalle                                        |
|------------------|------------------------------------------------|
| Contrato estable | JSON con `schema_version`                      |
| Estado           | ¿juego corriendo?, vehículo, mapa, throttle OK |
| Buffer           | Últimas N muestras (ej. 120 s a 10 Hz)         |
| Sesiones         | POST cuerpo = `TelemetrySession` simplificado  |

Tecnología sugerida: **FastAPI + uvicorn**, Python 3.11+.

### 3. Cliente en proyecto principal

Nuevo módulo futuro (no creado aún):

snowrunner real/
  telemetry_client.py   # GET sample, POST session

Sustituye o complementa:

powershell

 Hoy

python grabar_ce.py --live --import

 Futuro

python telemetry_client.py --record --import-via-api

## Flujos

### Flujo A — Monitor en vivo

UI / pedal_monitor  →  GET /v1/sample cada 100ms  →  API  →  agent

### Flujo B — Grabación sesión

1. POST /v1/sessions/start { protocol_hint?, vehicle_id? }
2. Agente empuja muestras al buffer
3. POST /v1/sessions/{id}/end
4. Principal: GET /v1/sessions/{id} → guarda en telemetria/sesiones/
5. Principal: comparar_telemetria.py (sin cambios de lógica MAE)

### Flujo C — Puente CSV (Fase 1)

API watch  ~/Documents/.../telemetria_ce_log.csv
         → parsea última fila como SampleV1
         → GET /v1/sample

Sin agente memoria; útil para validar cliente principal.

## Almacenamiento

| Dato               | v0                                          | v1+                                |
|--------------------|---------------------------------------------|------------------------------------|
| Muestras recientes | RAM (deque)                                 | + NDJSON opcional                  |
| Sesiones           | devuelve JSON al cliente; no persiste       | SQLite o archivos `data/sessions/` |
| Offsets            | read-only copy de `offsets_referencia.json` | sync desde principal               |

## Despliegue local (v0)

text
Terminal 1:  uvicorn snowrunner_telemetry_api.main:app --port 8765
Terminal 2:  SnowRunner.exe + snowrunner-telemetry-agent.exe   (Fase 2+)
Terminal 3:  snowrunner real — cliente import

Fase 1 solo requiere Terminal 1 + CSV existente de `grabar_ce.py`.

Bind: `127.0.0.1:8765`.

## Límites explícitos

La API **no**:

- modifica `initial.pak`
- ejecuta `compare_session_by_terrain`
- mantiene `calibracion.json` (eso es índice del principal)
- descubre offsets automáticamente en producción (solo reporta estado)

## Evolución

| Fase | Entregable                            |
|------|---------------------------------------|
| 0    | Docs (actual)                         |
| 1    | API + modo CSV (sin agente)           |
| 2    | Agente nativo C# + `/internal/ingest` |
| 3    | Sesiones + cliente en principal       |
| 4    | WebSocket stream                      |

Ver [ROADMAP.md](ROADMAP.md).
