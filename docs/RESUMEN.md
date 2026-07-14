# Resumen del proyecto — estado a julio 2026

Documento de **síntesis**: qué se hizo, qué se decidió, qué funciona hoy y qué sigue.

**Repositorio:** https://github.com/doski2/snowrunner-telemetry-api

---

## 1. Por qué existe este proyecto

`snowrunner real` (mod + sim + calibración) hoy lee memoria Havok, escribe CSV y analiza todo en el mismo árbol Python. Eso acopla adquisición y análisis.

**Objetivo:** separar en dos capas:

```
SnowRunner.exe → Agente (lectura) → API HTTP → snowrunner real (compare, sim, MAE)
```

SnowRunner **no tiene telemetría oficial** (SimHub, UDP, SDK). Todo depende de ingeniería inversa (`TRUCK_CONTROL`, Havok).

---

## 2. Cronología de la sesión

| Paso | Qué hicimos |
|------|-------------|
| **Investigación Q1** | API en **mismo PC**, `127.0.0.1:8765` |
| **Investigación Q2** | Cliente por **poll** (`GET /v1/sample`); WebSocket opcional Fase 4 |
| **Investigación Q3** | **Agente nativo C#** (Win32) en proceso aparte |
| **Investigación Q4** | Sesiones: **buffer en API** + JSON completo al `/end` |
| **Ecosistema externo** | [INVESTIGACION-ECOSISTEMA.md](INVESTIGACION-ECOSISTEMA.md) — no hay API lista en GitHub; FindMuck/Noclip como referencia RE |
| **GitHub** | Repo público `doski2/snowrunner-telemetry-api` creado y publicado |
| **Prueba en vivo** | Con juego en ralentí: probe OK (Fleetstar); throttle Fleetstar sin calibrar |
| **Fase 1** | FastAPI + 3 endpoints + tests; prueba manual con CSV Bandit |

---

## 3. Decisiones de arquitectura (cerradas)

| ID | Decisión |
|----|----------|
| Q1 | Mismo PC, localhost, sin LAN en v0 |
| Q2 | Poll para cliente; push agente→API en Fase 2 (`/internal/ingest`) |
| Q3 | Agente **C# .NET 8** (`OpenProcess`, `ReadProcessMemory`, lecturas batched) |
| Q4 | Grabación: `POST /sessions/start` → buffer → `POST /sessions/{id}/end` → `ce_session_v1` |
| Orden | **Fase 1 CSV** → **Fase 2 agente C#** → Fase 3 sesiones/cliente → Fase 4 WS |
| Transición | CSV legacy en paralelo hasta que el principal consuma la API |

Detalle: [INVESTIGACION.md](INVESTIGACION.md) §9, [ARQUITECTURA.md](ARQUITECTURA.md).

---

## 4. Estado por fases

### Fase 0 — Investigación ✅ (casi completa)

| Hecho | Documento / artefacto |
|-------|----------------------|
| Contexto y alcance | [CONTEXTO.md](CONTEXTO.md) |
| Alternativas A–G | [INVESTIGACION.md](INVESTIGACION.md) |
| Arquitectura agente C# + API Python | [ARQUITECTURA.md](ARQUITECTURA.md) |
| Contrato `ce_sample_v1` / `status_v1` | [CONTRATO-DATOS.md](CONTRATO-DATOS.md) |
| Repos y foros externos | [INVESTIGACION-ECOSISTEMA.md](INVESTIGACION-ECOSISTEMA.md) |
| Decisiones Q1–Q4 | [INVESTIGACION.md](INVESTIGACION.md) §9 |

**Pendiente Fase 0:** 0.8 — copiar fixtures JSON desde `snowrunner real/telemetria/sesiones/`.

### Fase 1 — API CSV ✅

| Componente | Ruta |
|------------|------|
| App FastAPI | `src/snowrunner_telemetry_api/main.py` |
| Parser CSV + última fila | `csv_source.py` |
| CSV → `ce_sample_v1` | `sample.py` |
| Columnas Havok | `csv_header.py` |
| Config / rutas | `config.py` |
| `vehicle_id` → mod id | `registry.py` |
| Detección juego Windows | `platform_win.py` |
| CLI uvicorn | `__main__.py` |
| Tests (9) | `tests/test_csv_parser.py`, `tests/test_api.py` |
| Fixture CSV | `fixtures/ce_log_snippet.csv` |

**Endpoints implementados:**

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/v1/health` | API viva, `agent_mode: csv` |
| GET | `/v1/status` | CSV, mtime, juego, vehículo, `probe_ok` |
| GET | `/v1/sample` | Última fila → JSON `ce_sample_v1` |

**Variables de entorno:**

| Variable | Default |
|----------|---------|
| `SNOWRUNNER_API_PORT` | `8765` |
| `SNOWRUNNER_CSV_PATH` | `%USERPROFILE%\Documents\My Games\SnowRunner\base\telemetria_ce_log.csv` |

### Fase 2+ — Pendiente

- Agente C# + `POST /internal/ingest`
- Sesiones `/start` / `/end`
- Cliente en `snowrunner real`
- WebSocket opcional

Ver [ROADMAP.md](ROADMAP.md).

---

## 5. Pruebas realizadas

### 5.1 API (Fase 1)

```powershell
pip install -e ".[dev]"
python -m snowrunner_telemetry_api
# GET http://127.0.0.1:8765/v1/health | /v1/status | /v1/sample
pytest   # 9 passed
```

**Resultado manual:** `/v1/sample` devolvió Bandit (`s_krs_58_bandit`), `terrain_kind: hard`, `map_name: Black River`, coherente con última fila del CSV (942 filas).

### 5.2 Juego en vivo (`grabar_ce.py --probe`)

Con SnowRunner corriendo (PID 23076), Fleetstar en Black River:

| Campo | Idle | Notas |
|-------|------|-------|
| `vehicle_id` | `s_fleetstar_f2070a` | OK |
| `speed_kmh` | 0 | OK |
| `terrain_kind` | hard | OK |
| `load_hint` | vacío, 6650 kg | OK |
| `throttle_input` | ~0.424 (gas on/off igual) | **Sin calibrar** — `throttle_input_src: None` |
| `throttle_motor` | 1.0 | Motor pide; input no fiable |

**Acción recomendada en principal:** `grabar_telemetria.bat drive_cal` para Fleetstar antes de MAE de pedal.

### 5.3 CSV en disco

Última grabación CSV conocida: **13 jul 2026** (Bandit cargado). No refleja la sesión Fleetstar actual. Para refrescar:

```powershell
cd "C:\Users\doski\snowrunner real"
python grabar_ce.py --duration 10 --interval 0.5
```

---

## 6. Hallazgos del ecosistema externo

- **No existe** proyecto GitHub con API HTTP de telemetría SnowRunner.
- **Más cercano:** [FindMuck/SnowRunner_Noclip](https://github.com/FindMuck/SnowRunner_Noclip) — mismos singletons `TRUCK_CONTROL`, `mappings.md` (offsets de build antiguo; validar vs `memoria_havok.py`).
- **SCS SDK** (ETS2): modelo de referencia; no aplica a SnowRunner.
- **SimHub:** sin soporte oficial.

Detalle: [INVESTIGACION-ECOSISTEMA.md](INVESTIGACION-ECOSISTEMA.md).

---

## 7. Estructura del repositorio

```
snowrunner-telemetry-api/
├── docs/           # Investigación, arquitectura, contrato, roadmap, resumen
├── fixtures/       # CSV de prueba (Fase 1); JSON sesiones (pendiente 0.8)
├── src/snowrunner_telemetry_api/
├── tests/
├── pyproject.toml
└── README.md
```

---

## 8. Reglas de throttle (Fase 1)

Si el CSV no trae `throttle_input`:

- Se usa `throttle` como input solo si **≠ -1** (grabaciones viejas no fiables).
- Respuesta incluye `throttle_input_legacy_fallback: true` cuando aplica.
- Implementación: `src/snowrunner_telemetry_api/sample.py`.

---

## 9. Próximos pasos sugeridos

| Prioridad | Tarea |
|-----------|--------|
| 1 | Copiar fixtures JSON (ROADMAP 0.8) |
| 2 | Grabar CSV fresco si se quiere API al día con Fleetstar |
| 3 | `drive_cal` Fleetstar en principal (throttle) |
| 4 | **Fase 2:** scaffold agente C# + spike `read_active_sample` |
| 5 | **Fase 3:** `/v1/sessions/start` y `/end` |

---

## 10. Enlaces

| Recurso | URL |
|---------|-----|
| Repo | https://github.com/doski2/snowrunner-telemetry-api |
| Proyecto principal | `../snowrunner real/` |
| Contrato datos | [CONTRATO-DATOS.md](CONTRATO-DATOS.md) |
| Roadmap | [ROADMAP.md](ROADMAP.md) |
