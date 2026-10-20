# Investigación — antes de probar la API

Documento de **recopilación y decisiones**. Objetivo: no escribir endpoints hasta entender alternativas, costes y contrato con `snowrunner real`.

**Estado jul 2026:** Fase **0** y **1** cerradas (API CSV). Fase **2.0** + **2.1** cerradas (agente C# spike). Combustible cerrado (`ce_fuel_hud`). Terreno por rueda portado (adelanto 2.2) con **modo saturado Bandit** (`+2BC`). Resto 2.2 pausado (batched + drive). Detalle: [ROADMAP.md §2.2](ROADMAP.md#fase-22--pendiente-recopilación-de-datos).

---

## 1. Preguntas que hay que responder

| # | Pregunta | Estado |
|---|----------|--------|
| Q1 | ¿La API corre en el **mismo PC** que el juego o en remoto? | **✅ Mismo PC** — `127.0.0.1` (localhost); agente + juego + API en la misma máquina |
| Q2 | ¿Stream (push) o poll (pull)? | **✅ Poll** — `GET /v1/sample` / `GET /v1/status`; stream (WS) solo Fase 4 si hace falta |
| Q3 | ¿Quién lee memoria: agente dedicado o el propio servidor API? | **✅ Agente dedicado nativo** (C#, proceso aparte) — ver §3 G |
| Q4 | ¿Sesión = archivo JSON completo o solo buffer + POST al cerrar? | **✅ Buffer en API + JSON completo al cerrar** — ver §9 / Flujo B en ARQUITECTURA |
| Q5 | ¿Versionar esquema (`schema_version` en cada muestra)? | **✅ Sí** — `ce_sample_v1` en `/v1/sample` y muestra del agente |
| Q6 | ¿Autenticación necesaria en localhost? | **No** en v0; sí si red LAN |
| Q7 | ¿Offset único de combustible en build jun-2026? | **✅ Sí** — `ce_fuel_hud` (`exe+2A8EDE0→…→f32+5E8`), validado multi-vehículo vs HUD; ver [INVESTIGACION-ECOSISTEMA.md §11.5](INVESTIGACION-ECOSISTEMA.md#115-ce-pointerscan-combustible-usuario-jul-2026) |
| Q8 | ¿Dashboard sin API (agente directo)? | **✅ Sí (adelanto)** — `run_dashboard.bat --source agent` parsea JSON stdout del exe; `POST /internal/ingest` sigue pendiente (2.4) |

---

## 2. Inventario del pipeline actual (hecho)

### Productores

| Componente | Salida | Notas |
|------------|--------|-------|
| `grabar_ce.py` + `memoria_havok.py` | CSV ~50 columnas | Principal, Python |
| `snowrunner-telemetry-agent` (C#) | JSON stdout (`--loop`) | Fase 2.1; memoria Havok + volante WinMM |
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
| API FastAPI (`GET /v1/sample`) | CSV o buffer futuro |
| Dashboard GUI (`run_dashboard.bat`) | Agente stdout **o** API CSV |

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

Proceso aparte que usa **Win32 directo** (`OpenProcess`, `ReadProcessMemory`; `VirtualQueryEx` previsto en Fase 2.2) y empuja muestras al API server Python.

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
| `VirtualQueryEx` para cache de regiones válidas (**Fase 2.2**, aún no en agente) | Offsets hay que mantener en C# *y* validar vs Python legacy |
| `.exe` sin intérprete; crash del lector no tumba la API | Curva inicial mayor que portar Python tal cual |
| Escala a 20–50 Hz sin GIL ni overhead ctypes | |

**Tecnología:** C# (.NET 8), P/Invoke `kernel32.dll`. C++ descartado salvo necesidad futura de binario sin runtime.

**Puente interno agente → API:** `POST http://127.0.0.1:8765/internal/ingest` con cuerpo `ce_sample_v1` JSON. La API no reexpone `/internal/*` al exterior.

**Referencia de port:** `snowrunner real/cheat_engine/memoria_havok.py`, `offsets_referencia.json`, `throttle_resolver.py`. Python sigue siendo fuente de verdad hasta que el spike Fase 2.6 pase.

**Cuándo:** Fase 2 (después de Fase 1 CSV). Fase 1 no requiere agente nativo.

**Alternativa descartada para el agente:** reutilizar Python/ctypes en el agente — mismo rendimiento limitado por syscall count; se mantiene solo en el principal durante transición.

---

### H. Script o mod que exponga / envíe datos — **¿es posible?**

SnowRunner **no ofrece** API de telemetría (ni UDP, ni shared memory, ni callbacks de mod). Cualquier solución es **ingeniería inversa** o herramienta **externa** al proceso del juego. Detalle ampliado en [INVESTIGACION-ECOSISTEMA.md](INVESTIGACION-ECOSISTEMA.md) §1–2.

#### H.1 Mod `.pak` oficial (contenido Saber)

Los mods publicables según [expeditions-guides.saber.games](https://expeditions-guides.saber.games/) limitan el alcance a **datos estáticos**: XML de camiones, addons, física de diseño, texturas, etc.

| ¿Puede un `.pak` enviar telemetría? | **No** en la práctica |
|-------------------------------------|------------------------|
| Scripting en runtime (Lua/C#) | No documentado; el motor no expone hooks de “cada frame” al modder |
| Leer velocidad / combustible HUD | Solo vía offsets en memoria, no vía API del juego |
| Abrir socket HTTP/UDP desde el mod | Requeriría código nativo inyectado, no un `.pak` XML |

**Conclusión:** un mod de contenido sirve para **enriquecer** `meta.setup` (masas, `vehicle_id`), no para sustituir el agente de memoria.

#### H.2 Script Cheat Engine Lua (externo — ya existía)

`TelemetryLogger.lua` en `snowrunner real/cheat_engine/` es el precedente más cercano a un “script que manda datos”: CE **adjunto** al proceso, lee punteros Havok y escribe CSV cada 500 ms.

Esquema equivalente al agente actual:

```lua
-- Patrón simplificado (legacy TelemetryLogger.lua / FindMuck Noclip)
local base = getAddress("SnowRunner.exe")
local tc   = readQword(base + TRUCK_CONTROL_OFF)
local veh  = readQword(tc + 0x8)
-- ... rigid body, velocidad, throttle ...
-- Salida: solo fichero local; CE Lua no tiene HTTP estándar
io.open(csv_path, "a"):write(line .. "\n")
```

| Pros | Contras |
|------|---------|
| Misma lógica que `memoria_havok.py` | CE abierto, frágil tras patches |
| Prototipo rápido | Sin `POST` nativo; CSV en Documents |
| | Mismos offsets que hay que mantener |

**Estado en este repo:** sustituido por `grabar_ce.py` → agente C# → `POST /internal/ingest`. El script CE sigue siendo útil como **referencia de punteros**, no como producto.

#### H.3 DLL inyectada / “plugin” estilo SCS SDK (teórico)

En ETS2/ATS el juego carga un plugin que rellena `Local\SCSTelemetry`. SnowRunner **no tiene** ese contrato. Una DLL comunitaria tendría que:

1. Inyectarse en `SnowRunner.exe` (manual map, `LoadLibrary`, etc.).
2. Hookear el loop de simulación o leer Havok cada tick.
3. Escribir shared memory o enviar UDP/HTTP.

Bosquejo (no existe proyecto mantenido para SnowRunner):

```csharp
// Hipotético — NO hay SDK Saber; offsets por build
[DllExport] static void TelemetryTick() {
    var liters = ReadFuel(vehiclePtr);      // mismos offsets que FuelReader.cs
    var speed  = ReadSpeed(rigidBodyPtr);
    // Opción A: shared memory (patrón SCS)
    Marshal.StructureToPtr(sample, mmap, false);
    // Opción B: socket (más frágil dentro del proceso del juego)
    // udp.Send(Encoding.UTF8.GetBytes(JsonSerializer.Serialize(sample)));
}
```

| Pros | Contras |
|------|---------|
| Latencia mínima dentro del proceso | **Riesgo** anti-cheat / integridad / EULA |
| Podría imitar SimHub | Cero repos estables en GitHub para SR |
| | Cada patch Steam puede romper hooks |
| | Más difícil de depurar que proceso externo |

**Decisión:** no perseguir DLL inyectada; el **agente C# externo** (§3 G) obtiene los mismos datos con `ReadProcessMemory` sin modificar el ejecutable.

#### H.4 Frida / trainer (spike de descubrimiento)

[tickelton/frida-snowrunner-trainer.py](https://github.com/tickelton/misc.re/blob/master/frida-snowrunner-trainer.py) escanea memoria para dinero/XP. Patrón útil para **buscar** offsets, no para producción de telemetría estructurada (vehículo, ruedas, terreno).

#### H.5 Lo que sí hace nuestro stack (recomendado)

El “script/mod que manda datos” en la arquitectura adoptada es el **agente nativo + API**, no un `.pak`.

**Flujo objetivo (Fase 2.4+):**

```
SnowRunner.exe  (sin modificar)
       ↑ ReadProcessMemory (externo)
snowrunner-telemetry-agent.exe
       │ POST /internal/ingest  ← pendiente 2.4
       ▼
FastAPI 127.0.0.1:8765  →  GET /v1/sample  →  snowrunner real
```

**Flujo actual (jul 2026, sin ingest):**

```
SnowRunner.exe
       ↑ ReadProcessMemory
snowrunner-telemetry-agent.exe  --loop-->  JSON stdout
       │                                      │
       │ (2.4 pendiente)                      ├─ run_dashboard.bat --source agent
       ▼                                      └─ run_agent.bat (diagnóstico)
FastAPI  ← CSV telemetria_ce_log.csv  ← grabar_ce.py
       │
       └─ run_dashboard.bat --source api
```

Cuerpo mínimo que el agente ya empujará (contrato `ce_sample_v1`):

```json
{
  "schema_version": "ce_sample_v1",
  "vehicle_id": "s_fleetstar_f2070a",
  "speed_kmh": 12.4,
  "fuel_pct": 93.3,
  "fuel_liters": 196.0,
  "throttle_input": "0.42",
  "throttle_motor": "0.38",
  "probe_ok": true
}
```

Cliente de prueba sin mod:

```powershell
curl http://127.0.0.1:8765/v1/sample
.\run_dashboard.bat --source agent
```

#### H.5b Datos estáticos desde `initial.pak` (oct 2026)

`preload\paks\client\initial.pak` es un **zip con XML legibles** (11 719 entradas: `classes/trucks`, `classes/wheels`, `terrain_layers`, `_templates/trucks.xml`). No requiere tocar el proceso del juego. `scripts/extract_game_catalog.py` (solo lectura) genera `data/game_catalog.json` (ignorado en git):

| Dato | Origen | Uso |
|------|--------|-----|
| `FuelCapacity` por camión (118 camiones) | `classes/trucks/*.xml` | Validar `fuel_liters`/`fuel_pct` de `ce_fuel_hud` (Bandit = 150 L base) |
| `BodyFriction`, `BodyFrictionAsphalt`, `SubstanceFriction` por tipo de neumático | `_templates/trucks.xml` | Calibrar el clasificador de terreno con valores reales del motor |
| `IsAsphalt`, `IsWetnessAsIce`, etc. por capa de terreno | `classes/terrain_layers/*.xml` | Mapeo de materiales |

Límites: son valores **base** (los addons de depósito cambian la capacidad) y los IDs de camión de los XML no coinciden con `vehicle_id` (`s_*`); falta la tabla de equivalencias. `shared.pak` (2 GB) contiene solo mallas.

#### H.6 Tabla resumen — ¿qué camino usar?

| Enfoque | ¿Envía datos en vivo? | ¿Mantenible? | Veredicto |
|---------|------------------------|--------------|-----------|
| Mod `.pak` XML | No | Alta para contenido | Solo datos estáticos |
| CE Lua (`TelemetryLogger`) | Sí → CSV | Media | Legacy / referencia |
| Agente C# externo | Sí → HTTP | Media (offsets) | **Adoptado** (Fase 2) |
| DLL inyectada | Sí (teórico) | Baja | Descartado |
| Frida | Parcial | Baja | Solo investigación |
| API oficial Saber | — | — | **No existe** |

**Respuesta corta:** sí es posible **mandar datos**, pero no con un mod de contenido normal; hace falta un **proceso o script externo** (o inyección avanzada). Este proyecto implementa la vía externa más segura y alineada con SimHub/SCS como diseño objetivo ([INVESTIGACION-ECOSISTEMA.md](INVESTIGACION-ECOSISTEMA.md) §6).

#### H.7 CLI del agente (`agent/Program*.cs`, Fase 2.1)

Punto de entrada: `Program.cs` (muestra JSON + flags de entrada). Sesión compartida en `Program.Session.cs` (`GameSession`: offsets, PID, módulo, `read_active_sample`). Diagnóstico combustible en `Program.FuelScan.cs` y `Program.FuelDiff.cs`.

| Comando | Efecto |
|---------|--------|
| `.\run_agent.bat` | Una muestra JSON (`vehicle_id`, `speed_kmh`, `fuel_*`, `terrain_*`, throttle) |
| `.\run_agent.bat --loop --interval=500` | Poll continuo (stdout JSON compacto) |
| `.\run_agent.bat --memory-only` | Sin volante; throttle desde Havok |
| `.\run_agent.bat --fuel-scan --target-liters=171` | Busca offsets que coinciden con litros HUD |
| `.\run_agent.bat --fuel-diff [--wait=5000]` | Snapshot antes/después; conducir o repostar en la espera |
| `.\run_agent.bat --fuel-debug` | Probes `FuelReader` + cadena CE `ce_fuel_hud` (prioridad) |
| `.\run_agent.bat --wheel-debug` | Por rueda: `+2FC/+2F8/+2F4`, `+2B4`, `+2EC/+2E8`, `terrain_kind` |
| `.\run_agent.bat --list-devices` / `--watch-input` | Diagnóstico volante (WinMM → DirectInput → XInput) |
| `.\run_dashboard.bat --source agent` | GUI en vivo sin API (parsea stdout del agente) |
| `.\run_dashboard.bat --source agent --compare` | Terreno agente vs última fila CSV (requiere API + `grabar_ce.py`) |

**Volante:** con SnowRunner abierto, DirectInput suele estar bloqueado; prioridad **WinMM eje RZ** (VelocityOne → `joy0`).

Códigos de salida: `0` OK · `1` juego no en ejecución · `2` offsets/memoria · `3` probe fallido (cadena Havok o muestra incompleta).

Checklist combustible en vivo: [INVESTIGACION-ECOSISTEMA.md §11.3](INVESTIGACION-ECOSISTEMA.md#113-checklist-de-validación---fuel-scan---fuel-diff).

Paridad terreno agente ↔ Python: `scan_wheel_substance.py` + `grabar_ce.py --probe` (raíz del principal, no `cheat_engine/`). Validación Bandit jul 2026: [ROADMAP.md §2.2](ROADMAP.md#terreno--validación-bandit-jul-2026-black-river).

---

## 4. Arquitectura recomendada (síntesis)

Ver [ARQUITECTURA.md](ARQUITECTURA.md). Resumen:

```
┌──────────────────┐
│  Agent C#        │  ← OpenProcess / ReadProcessMemory (VirtualQueryEx → 2.2)
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

**Fase 0:** documentación + contrato — ✅  
**Fase 1:** API lee CSV existente (alternativa E) — ✅  
**Fase 2:** agente nativo C# (alternativa G) — **2.0/2.1 ✅**, 2.2 pausada, 2.4+ pendiente  
**Fase 3:** sesiones + cliente principal — cola  
**Fase 4:** WebSocket stream — opcional

---

## 5. Pasos previos (checklist investigación)

### 5.1 Contrato y esquema

- [x] Copiar referencia de `CSV_HEADER` y campos `TelemetrySample` → [CONTRATO-DATOS.md](CONTRATO-DATOS.md)
- [x] Definir `schema_version` (ej. `ce_sample_v1`)
- [x] Listar campos **obligatorios** vs **opcionales** para import en principal
- [ ] Documentar mapeo `vehicle_id` CE → mod (`registry.py`) en contrato compartido

### 5.2 Port al agente nativo (Fase 2)

- [x] Spike `read_active_sample` en C# (`ActiveSampleReader`, Fase 2.1)
- [x] Carga `offsets_referencia.json` + `ThrottleResolver` portado (adelanto 2.3)
- [x] CLI diagnóstico combustible (`--fuel-scan`, `--fuel-diff`, `--fuel-debug`) — ver [§3 H.7](#h7-cli-del-agente-agentprogramcs-fase-21)
- [x] Terreno por rueda en C# (`WheelTerrainReader`, `--wheel-debug`) — paridad con `read_wheel_terrain` (jul 2026)
- [ ] Inventariar qué **portar a C#** desde el principal:
  - `memoria_havok.py` — lectura Havok **batched** + drive (2.2; terreno puntual ya portado)
  - `throttle_resolver.py` — paridad Python + env (2.3)
  - Loop de muestreo de `grabar_ce.py` — intervalo configurable + `POST /internal/ingest` (2.4)
- [ ] Qué **queda** en principal: `importar_ce_csv`, compare, index, `grabar_ce.py` legacy durante transición
- [x] `offsets_referencia.json` versionado junto al agente (`agent/data/`)
- [x] Entrada física volante: WinMM eje RZ cuando DirectInput bloqueado (VelocityOne + juego abierto)

**Spike agente vs contrato completo** (subset jul 2026; ver [CONTRATO-DATOS.md](CONTRATO-DATOS.md)):

| Campo | Agente 2.1 / adelanto 2.2 | CSV / sesión completa |
|-------|---------------------------|------------------------|
| `vehicle_id`, `speed_kmh`, `throttle_*` | ✅ | ✅ |
| `fuel_pct`, `fuel_liters`, `fuel_source` | ✅ (`ce_fuel_hud`) | ✅ (CSV) |
| `probe_ok`, `chain` | ✅ (diagnóstico) | — |
| `terrain_kind`, `wheel_grip`, `mud_grade`, agregados rueda | ✅ (= Python; modo saturado Bandit jul 2026) | ✅ |
| Drive batched, `VirtualQueryEx` | ⬜ 2.2 | ✅ |

**Terreno (jul 2026):** modo **saturado** cuando `+2FC/+2EC≈1.0` en todas las ruedas (Bandit): discrimina con `+2B4` agregado y `+2BC`. Ver [ROADMAP.md](ROADMAP.md#terreno--validación-bandit-jul-2026-black-river) y `tests/test_terrain_classifier.py`.

### 5.3 Entorno y despliegue

- [x] Python 3.11+ (alineado con principal)
- [x] Puerto por defecto `8765` — `SNOWRUNNER_API_PORT`
- [ ] Variables agente en runtime: `SNOWRUNNER_AGENT_INGEST_URL`, `SNOWRUNNER_AGENT_INTERVAL_MS`, `SNOWRUNNER_OFFSETS_PATH` (documentadas; ingest pendiente 2.4)
- [ ] Log: NDJSON de muestras para replay sin juego

### 5.4 Calidad de datos

- [ ] Preflight equivalente a `calibrar_drive.preflight_check` expuesto en `GET /status`
- [ ] Flag `throttle_input_ok` por vehículo
- [ ] Rechazar sesiones con >50 % `terrain_kind` vacío (regla `datos/README.md`)

### 5.5 Seguridad

- [x] v0: bind `127.0.0.1` only (`config.py` → `DEFAULT_HOST`)
- [x] Lectura de memoria = mismo riesgo que CE hoy; documentar en README
- [ ] No exponer rutas absolutas del usuario en respuestas API

### 5.6 Pruebas sin juego

- [x] Fixture CSV + tests parser (`tests/test_csv_parser.py`)
- [x] Tests API `/v1/health`, `/status`, `/sample` (`tests/test_api.py`)
- [x] Tests dashboard (`tests/test_dashboard.py`)
- [ ] Fixture: `fixtures/sample_bandit_idle.json` (ROADMAP 0.8)
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

## 7. Endpoints

| Método | Ruta | Descripción | Estado |
|--------|------|-------------|--------|
| GET | `/v1/health` | API viva | ✅ Fase 1 |
| GET | `/v1/status` | csv path, mtime, modo agente inferido | ✅ Fase 1 |
| GET | `/v1/sample` | última muestra normalizada `ce_sample_v1` | ✅ Fase 1 (CSV) |
| GET | `/v1/samples?since=t` | buffer reciente | ⬜ |
| POST | `/v1/sessions/start` | inicia grabación; API crea buffer + `session_id` | ⬜ Fase 3 |
| POST | `/v1/sessions/{id}/end` | cierra grabación; devuelve `ce_session_v1` completo | ⬜ Fase 3 |
| GET | `/v1/sessions/{id}` | recuperar sesión ya cerrada | ⬜ Fase 3 |
| POST | `/internal/ingest` | **solo localhost** — agente C# empuja `ce_sample_v1` | ⬜ Fase 2.4 |
| WS | `/v1/stream` | muestras en tiempo real | ⬜ Fase 4 |

Lista completa de tareas: [ROADMAP.md](ROADMAP.md).

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
| 9 | ¿Mod/script in-game en lugar de agente? | **No** — `.pak` no expone runtime; CE Lua = legacy; **agente externo** = camino adoptado (§3 H) |
| 10 | ¿Pedal con volante y juego abierto? | **WinMM eje RZ** primero; DirectInput suele bloqueado con SnowRunner en ejecución |
| 11 | ¿Monitor en vivo sin ingest? | **Dashboard** `--source agent` (stdout) o `--source api` (CSV) — ver Q8 |

**Implicaciones Q1:**

- Agente C# y `SnowRunner.exe` comparten máquina (lectura RAM obligatoria).
- API y agente en localhost; `snowrunner real` consume por `http://127.0.0.1:8765`.
- Análisis remoto futuro solo vía JSON exportado o sesión POST, no lectura de memoria a distancia.

**Implicaciones Q4:**

- Durante grabación: agente → `POST /internal/ingest` → buffer RAM en la API (no sesión parcial al cliente).
- Al cerrar: `POST /v1/sessions/{id}/end` ensambla `meta` + `samples[]` → mismo contrato que `TelemetrySession`.
- El principal guarda el JSON en `telemetria/sesiones/` y ejecuta `comparar_telemetria` sin cambios de lógica MAE.
- Monitor en vivo sigue siendo poll (`GET /v1/sample`); sesión ≠ stream.

**Fase 0 cerrada** en decisiones Q1–Q4. **Fase 1** API CSV implementada. **Fase 2.0/2.1** agente spike cerrado; **2.2 pausada** (combustible + batched Havok). Pendiente ROADMAP 0.8 (fixtures JSON sesión), 2.4 (ingest), 2.6 (paridad vs `grabar_ce.py`).

Ver [RESUMEN.md](RESUMEN.md) · [ROADMAP.md](ROADMAP.md) · [INVESTIGACION-ECOSISTEMA.md](INVESTIGACION-ECOSISTEMA.md)
