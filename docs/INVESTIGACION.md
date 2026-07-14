# Investigación — antes de probar la API

Documento de **recopilación y decisiones**. Objetivo: no escribir endpoints hasta entender alternativas, costes y contrato con `snowrunner real`.

---

## 1. Preguntas que hay que responder

| # | Pregunta | Estado |
|---|----------|--------|
| Q1 | ¿La API corre en el **mismo PC** que el juego o en remoto? | **✅ Mismo PC** — `127.0.0.1` (localhost); agente + juego + API en la misma máquina |
| Q2 | ¿Stream (push) o poll (pull)? | **✅ Poll** — `GET /v1/sample` / `GET /v1/status`; stream (WS) solo Fase 4 si hace falta |
| Q3 | ¿Quién lee memoria: agente dedicado o el propio servidor API? | **✅ Agente dedicado nativo** (C#, proceso aparte) — ver §3 G |
| Q4 | ¿Sesión = archivo JSON completo o solo buffer + POST al cerrar? | **✅ Buffer en API + JSON completo al cerrar** — ver §9 / Flujo B en ARQUITECTURA |
| Q5 | ¿Versionar esquema (`schema_version` en cada muestra)? | **Recomendado: sí** |
| Q6 | ¿Autenticación necesaria en localhost? | **No** en v0; sí si red LAN |

---

## 2. Inventario del pipeline actual (hecho)

### Productores

| Componente | Salida | Notas |
|------------|--------|-------|
| `grabar_ce.py` + `memoria_havok.py` | CSV ~50 columnas | Principal, Python |
| `TelemetryLogger.lua` | Mismo CSV | Legacy CE |
| `grabar_telemetria.bat` | CSV + import automático | Orquestador |

### Transformación

| Paso | Entrada | Salida |
|------|---------|--------|
| `importar_ce_csv.py` | CSV | `TelemetrySession` JSON |
| `datos/map_detect.py` | CSV / log / memoria | `meta.session_context` |
| `datos/catalog_lookup.py` | catálogo XML | `setup` enriquecido |

### Consumidores

| Componente | Usa |
|------------|-----|
| `comparar_telemetria.py` | JSON sesión + sim |
| `indexar_sesion.py` | MAE → `calibracion.json` |
| `consultar_base.py` | manifest + sesiones |
| `camiones/*/simulador.py` | meta protocolo |

### Punto de fricción conocido

- Columna `throttle` en CSV antiguo **no fiable** (valores -1.0 con velocidad alta).
- Solución en principal: `throttle_input` + `throttle_motor` + `throttle_resolver` por vehículo.
- **La API debe emitir siempre los tres campos** cuando existan offsets.

---

## 3. Alternativas de integración

### A. REST + polling (recomendada para v0)

```
Cliente (snowrunner real)  --GET /v1/status-->  API
                         --GET /v1/sample-->   última muestra
                         --POST /v1/sessions--> subir sesión completa
```

| Pros | Contras |
|------|---------|
| Simple, debug con `curl` | Latencia ~intervalo de poll |
| Fácil de testear | No ideal para >10 Hz sin carga |

**Cuándo:** importación batch, scripts `grabar_telemetria` adaptado, CI con fixtures.

---

### B. WebSocket / SSE (stream)

```
Agente  --WS-->  API  --WS/SSE-->  clientes (monitor, grabador)
```

| Pros | Contras |
|------|---------|
| Baja latencia, muchas muestras/s | Más complejidad, reconexión |
| Bueno para `pedal_monitor` remoto | Tests más difíciles |

**Cuándo:** monitor en vivo, dashboard, segunda pantalla.

---

### C. Carpeta compartida / file watcher (sin HTTP)

```
Agente escribe  out/samples.ndjson
Principal usa   watchdog → importar
```

| Pros | Contras |
|------|---------|
| Cero servidor HTTP | Acoplamiento a paths, locks en Windows |
| Muy rápido de prototipar | No escala a red |

**Cuándo:** spike de 1 día; migrar a REST después.

---

### D. gRPC / protobuf

| Pros | Contras |
|------|---------|
| Contrato fuerte, eficiente | Overkill para un usuario / un PC |
| | Curva para scripts Python del principal |

**Cuándo:** descartado en v0 salvo necesidad multi-idioma.

---

### E. Reutilizar CSV como “API” (status quo mejorado)

API solo **normaliza y sirve** el CSV existente:

```
GET /v1/csv/latest  →  parsea telemetria_ce_log.csv
```

| Pros | Contras |
|------|---------|
| Casi cero cambio en agente | Sigue atado a ruta Documents |
| | No resuelve desacoplamiento real |

**Cuándo:** puente temporal mientras se extrae `memoria_havok` al agente.

---

### F. Agente embebido en el proyecto principal (no separar)

Un solo proceso: lector + FastAPI en `snowrunner real/api/`.

| Pros | Contras |
|------|---------|
| Un repo, menos sync de contrato | **No cumple** el objetivo de dividir |
| | Mezcla mod/sim con adquisición |

**Decisión:** rechazado; la API vive en **este** repo.

---

### G. Agente nativo Windows (C#) — **DECISIÓN ADOPTADA** para Fase 2

Proceso aparte que usa **Win32 directo** (`OpenProcess`, `ReadProcessMemory`, `VirtualQueryEx`) y empuja muestras al API server Python.

```
SnowRunner.exe
    → Agente C# (snowrunner-telemetry-agent.exe)
        → POST /internal/ingest  (localhost)
    → API FastAPI (este repo)
        → GET /v1/sample
    → snowrunner real
```

| Pros | Contras |
|------|---------|
| Máximo control y rendimiento en lectura RAM | Portar lógica desde `memoria_havok.py` (~2200 líneas) |
| Lecturas **batched** (un bloque por `hkpRigidBody` / rueda) | Dos runtimes: .NET + Python |
| `VirtualQueryEx` para cache de regiones válidas | Offsets hay que mantener en C# *y* validar vs Python legacy |
| `.exe` sin intérprete; crash del lector no tumba la API | Curva inicial mayor que portar Python tal cual |
| Escala a 20–50 Hz sin GIL ni overhead ctypes | |

**Tecnología:** C# (.NET 8), P/Invoke `kernel32.dll`. C++ descartado salvo necesidad futura de binario sin runtime.

**Puente interno agente → API:** `POST http://127.0.0.1:8765/internal/ingest` con cuerpo `ce_sample_v1` JSON. La API no reexpone `/internal/*` al exterior.

**Referencia de port:** `snowrunner real/cheat_engine/memoria_havok.py`, `offsets_referencia.json`, `throttle_resolver.py`. Python sigue siendo fuente de verdad hasta que el spike Fase 2.6 pase.

**Cuándo:** Fase 2 (después de Fase 1 CSV). Fase 1 no requiere agente nativo.

**Alternativa descartada para el agente:** reutilizar Python/ctypes en el agente — mismo rendimiento limitado por syscall count; se mantiene solo en el principal durante transición.

---

## 4. Arquitectura recomendada (síntesis)

Ver [ARQUITECTURA.md](ARQUITECTURA.md). Resumen:

```
┌──────────────────┐
│  Agent C#        │  ← OpenProcess / ReadProcessMemory / VirtualQueryEx
│  snowrunner-     │     port de memoria_havok + offsets_referencia.json
│  telemetry-agent │
└────────┬─────────┘
         │ POST /internal/ingest (localhost)
┌────────▼─────────┐
│  API Server      │  ← FastAPI (Python, este repo)
│  (este proyecto) │
└────────┬─────────┘
         │ GET/POST JSON /v1/*
┌────────▼─────────┐
│  snowrunner real │  ← cliente: importar vía HTTP
└──────────────────┘
```

**Fase 0:** documentación + contrato.  
**Fase 1:** API lee CSV existente (alternativa E).  
**Fase 2:** agente nativo C# con memoria propia (alternativa G).  
**Fase 3:** sesiones + cliente principal.  
**Fase 4:** WebSocket stream.

---

## 5. Pasos previos (checklist investigación)

### 5.1 Contrato y esquema

- [ ] Copiar referencia de `CSV_HEADER` y campos `TelemetrySample` → [CONTRATO-DATOS.md](CONTRATO-DATOS.md)
- [ ] Definir `schema_version` (ej. `ce_sample_v1`)
- [ ] Listar campos **obligatorios** vs **opcionales** para import en principal
- [ ] Documentar mapeo `vehicle_id` CE → mod (`registry.py`)

### 5.2 Port al agente nativo (Fase 2, no hacer en Fase 1)

- [ ] Inventariar qué **portar a C#** desde el principal:
  - `memoria_havok.py` — lectura Havok (referencia; implementación nativa con lecturas batched)
  - `offsets_referencia.json` — copia versionada junto al `.exe`
  - `throttle_resolver.py` — specs por vehículo
  - Loop de muestreo de `grabar_ce.py` — intervalo configurable, sin CSV intermedio
- [ ] Qué **queda** en principal: `importar_ce_csv`, compare, index, `grabar_ce.py` legacy durante transición
- [ ] Spike: `read_active_sample` mínimo en C# antes del port completo

### 5.3 Entorno y despliegue

- [ ] Python 3.11+ (alineado con principal)
- [ ] Puerto por defecto (ej. `8765`) — evitar conflicto con juego
- [ ] Variables API: `SNOWRUNNER_API_PORT` (default `8765`)
- [ ] Variables agente: `SNOWRUNNER_AGENT_INGEST_URL`, `SNOWRUNNER_AGENT_INTERVAL_MS` (default `100`), `SNOWRUNNER_OFFSETS_PATH`
- [ ] Log: NDJSON de muestras para replay sin juego

### 5.4 Calidad de datos

- [ ] Preflight equivalente a `calibrar_drive.preflight_check` expuesto en `GET /status`
- [ ] Flag `throttle_input_ok` por vehículo
- [ ] Rechazar sesiones con >50 % `terrain_kind` vacío (regla `datos/README.md`)

### 5.5 Seguridad

- [ ] v0: bind `127.0.0.1` only
- [ ] Lectura de memoria = mismo riesgo que CE hoy; documentar en README
- [ ] No exponer rutas absolutas del usuario en respuestas API

### 5.6 Pruebas sin juego

- [ ] Fixture: `fixtures/sample_bandit_idle.json`
- [ ] Fixture: `fixtures/session_ck1500_f2_snippet.json` (desde `telemetria/sesiones/`)
- [ ] Test contrato: campos que exige `importar_ce_csv.csv_row_to_sample`

---

## 6. Riesgos

| Riesgo | Mitigación |
|--------|------------|
| Update Steam rompe offsets | API reporta `offsets_build` + `probe_ok`; agente versionado |
| Duplicar lógica Python ↔ C# | Contrato único en CONTRATO-DATOS; Fase 2.6 compara vs `grabar_ce.py --probe` |
| Divergencia agente nativo vs CE legacy | Spike mínimo antes del port; offsets en JSON compartido |
| API innecesariamente grande | Empezar con 3 endpoints: status, sample, session |
| Latencia alta en poll | Intervalo configurable; luego WebSocket |
| throttle mal calibrado | Resolver en agente; status con `input_spec` usado |

---

## 7. Endpoints candidatos (no implementados)

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/v1/health` | API viva |
| GET | `/v1/status` | juego, PID, vehículo, offsets, mapa |
| GET | `/v1/sample` | última muestra normalizada |
| GET | `/v1/samples?since=t` | buffer reciente |
| POST | `/v1/sessions/start` | inicia grabación; API crea buffer + `session_id` |
| POST | `/v1/sessions/{id}/end` | cierra grabación; devuelve `ce_session_v1` completo |
| GET | `/v1/sessions/{id}` | recuperar sesión ya cerrada |
| POST | `/internal/ingest` | **solo localhost** — agente C# empuja `ce_sample_v1` |
| WS | `/v1/stream` | muestras en tiempo real |

**Ninguno está implementado** — lista para validar en ROADMAP.

---

## 8. Referencias en el proyecto principal

| Tema | Archivo |
|------|---------|
| CSV columnas | `cheat_engine/memoria_havok.py` → `CSV_HEADER` |
| Sesión JSON | `telemetria.py` → `TelemetrySession` |
| Import | `importar_ce_csv.py` |
| Metadatos | `datos/session_context.py` |
| Vehículos | `camiones/registry.py` |
| Offsets | `cheat_engine/offsets_referencia.json` |
| Plan datos | `docs/PLAN-BASE-DATOS-JUEGO.md` |
| Fase CE | `docs/FASE-6.md` |

---

## 9. Decisiones cerradas

| # | Pregunta | Decisión |
|---|----------|----------|
| 1 | ¿Empezamos por CSV o directamente memoria? | **E → G** — Fase 1 CSV; Fase 2 agente nativo |
| 2 | ¿CSV local en paralelo durante transición? | **Sí**; API como fuente preferida cuando esté lista |
| 3 | ¿Lenguaje del agente de memoria? | **C# (.NET 8)** con Win32 — alternativa G |
| 4 | ¿Quién lee memoria? | **Agente dedicado** en proceso aparte (Q3) |
| 5 | ¿Nombre de artefactos? | `snowrunner_telemetry_api` (Python), `snowrunner-telemetry-agent` (C# exe) |
| 6 | ¿Dónde corre la API? (Q1) | **Mismo PC** que el juego; bind `127.0.0.1:8765`; sin exposición LAN en v0 |
| 7 | ¿Cómo consume el cliente? (Q2) | **Poll** — `GET /v1/sample` periódico; WebSocket en Fase 4 opcional |
| 8 | ¿Formato de sesión? (Q4) | **Buffer en API** durante grabación; **JSON completo** (`ce_session_v1`) en `/end` |

**Implicaciones Q1:**

- Agente C# y `SnowRunner.exe` comparten máquina (lectura RAM obligatoria).
- API y agente en localhost; `snowrunner real` consume por `http://127.0.0.1:8765`.
- Análisis remoto futuro solo vía JSON exportado o sesión POST, no lectura de memoria a distancia.

**Implicaciones Q4:**

- Durante grabación: agente → `POST /internal/ingest` → buffer RAM en la API (no sesión parcial al cliente).
- Al cerrar: `POST /v1/sessions/{id}/end` ensambla `meta` + `samples[]` → mismo contrato que `TelemetrySession`.
- El principal guarda el JSON en `telemetria/sesiones/` y ejecuta `comparar_telemetria` sin cambios de lógica MAE.
- Monitor en vivo sigue siendo poll (`GET /v1/sample`); sesión ≠ stream.

**Fase 0 cerrada** en decisiones Q1–Q4. Pendiente solo 0.8 (fixtures JSON). **Fase 1 API CSV** implementada.

Ver [RESUMEN.md](RESUMEN.md) · [ROADMAP.md](ROADMAP.md) · [INVESTIGACION-ECOSISTEMA.md](INVESTIGACION-ECOSISTEMA.md)
