# Roadmap — hasta la primera prueba de API

Checklist por fases. **No marcar Fase 1 completa** hasta cerrar decisiones en [INVESTIGACION.md](INVESTIGACION.md) §9.

---

## Fase 0 — Investigación y documentación ✅ en curso

| # | Tarea | Estado |
|---|-------|--------|
| 0.1 | Crear repo/carpeta `snowrunner-telemetry-api` | ✅ |
| 0.2 | Documentar contexto y necesidad | ✅ [CONTEXTO.md](CONTEXTO.md) |
| 0.3 | Recopilar alternativas y pasos | ✅ [INVESTIGACION.md](INVESTIGACION.md) |
| 0.4 | Borrador arquitectura | ✅ [ARQUITECTURA.md](ARQUITECTURA.md) |
| 0.5 | Contrato de datos | ✅ [CONTRATO-DATOS.md](CONTRATO-DATOS.md) |
| 0.6 | Enlazar desde README del proyecto principal | ✅ `docs/API-PROYECTO-HERMANO.md` |
| 0.7 | Cerrar decisiones Q1–Q4 INVESTIGACION | ✅ |
| 0.8 | Copiar 2–3 fixtures JSON desde `telemetria/sesiones/` | ⬜ |
| 0.9 | Ecosistema externo (GitHub, foros) | ✅ [INVESTIGACION-ECOSISTEMA.md](INVESTIGACION-ECOSISTEMA.md) |

**Criterio de salida:** decisiones Q1–Q4 tomadas; contrato revisado.

---

## Fase 1 — API mínima (modo CSV, sin memoria)

Objetivo: `curl http://127.0.0.1:8765/v1/sample` devuelve última fila del CSV del juego **sin abrir nuevo código CE en el principal**.

| # | Tarea | Estado |
|---|-------|--------|
| 1.1 | `pyproject.toml` + FastAPI + uvicorn | ⬜ |
| 1.2 | `GET /v1/health` | ⬜ |
| 1.3 | `GET /v1/status` (csv path, file mtime, game inferido) | ⬜ |
| 1.4 | `GET /v1/sample` → `ce_sample_v1` | ⬜ |
| 1.5 | Parser CSV alineado con `CSV_HEADER` actual | ⬜ |
| 1.6 | Mapeo `throttle` viejo → documentar si falta `throttle_input` | ⬜ |
| 1.7 | Tests unitarios parser (fixture CSV) | ⬜ |
| 1.8 | README con comandos `curl` | ⬜ |

**Criterio de salida:** prueba manual con `telemetria_ce_log.csv` existente del Bandit.

---

## Fase 2 — Agente nativo C# (memoria)

Proyecto: `agent/` → `snowrunner-telemetry-agent` (.NET 8, win-x64).

| # | Tarea | Estado |
|---|-------|--------|
| 2.0 | Scaffold `agent/SnowrunnerTelemetryAgent.csproj` + P/Invoke kernel32 | ⬜ |
| 2.1 | Spike: `OpenProcess` + `read_active_sample` mínimo (speed, vehicle_id, throttle) | ⬜ |
| 2.2 | Port lecturas batched Havok (rigid body, ruedas, drive) desde `memoria_havok.py` | ⬜ |
| 2.3 | Cargar `offsets_referencia.json`; `throttle_resolver` portado | ⬜ |
| 2.4 | Loop muestreo + `POST /internal/ingest` → API buffer | ⬜ |
| 2.5 | `GET /v1/status` con `probe_ok`, `agent_version`, `throttle_spec` | ⬜ |
| 2.6 | Comparar muestra API vs `grabar_ce.py --probe` (ε en speed, vehicle_id, throttle_input) | ⬜ |

**Criterio de salida:** agente C# estable a 10 Hz; muestras indistinguibles del Python legacy en campos obligatorios.

---

## Fase 3 — Sesiones y cliente principal

| # | Tarea | Estado |
|---|-------|--------|
| 3.1 | `POST /v1/sessions/start`, `/end` + `GET /v1/sessions/{id}` | ⬜ |
| 3.2 | `telemetry_client.py` en `snowrunner real` | ⬜ |
| 3.3 | Flag en `grabar_telemetria.bat`: `--via-api` | ⬜ |
| 3.4 | Import + compare sin CSV intermedio | ⬜ |

---

## Fase 4 — Stream (opcional)

| # | Tarea | Estado |
|---|-------|--------|
| 4.1 | WebSocket `/v1/stream` | ⬜ |
| 4.2 | Adaptar `pedal_monitor` a API | ⬜ |

---

## Primera prueba definida (Fase 1)

Cuando Fase 1 esté lista:

```powershell
# Terminal A — API (futuro)
cd snowrunner-telemetry-api
uvicorn snowrunner_telemetry_api.main:app --port 8765

# Terminal B — comprobar
curl http://127.0.0.1:8765/v1/health
curl http://127.0.0.1:8765/v1/status
curl http://127.0.0.1:8765/v1/sample
```

**Éxito:** JSON con `vehicle_id`, `speed_kmh`, `schema_version`; coherente con última línea del CSV en Documents.

---

## Qué no hacer antes de Fase 1

- No crear el proyecto C# del agente (Fase 2).
- No cambiar `importar_ce_csv.py` en el principal.
- No publicar API en LAN sin autenticación.
- No duplicar `comparar_telemetria` en este repo.
