# Roadmap — hasta la primera prueba de API

Checklist por fases. Síntesis global: [RESUMEN.md](RESUMEN.md).

---

## Fase 0 — Investigación y documentación ✅

| # | Tarea | Estado |
|---|---|--------|
| 0.1 | Crear repo/carpeta `snowrunner-telemetry-api` | ✅ |
| 0.2 | Documentar contexto y necesidad | ✅ [CONTEXTO.md](CONTEXTO.md) |
| 0.3 | Recopilar alternativas y pasos | ✅ [INVESTIGACION.md](INVESTIGACION.md) |
| 0.4 | Borrador arquitectura | ✅ [ARQUITECTURA.md](ARQUITECTURA.md) |
| 0.5 | Contrato de datos | ✅ [CONTRATO-DATOS.md](CONTRATO-DATOS.md) |
| 0.6 | Enlazar desde README del proyecto principal | ✅ `docs/API-PROYECTO-HERMANO.md` |
| 0.7 | Cerrar decisiones Q1–Q4 INVESTIGACION | ✅ |
| 0.8 | Copiar 2–3 fixtures JSON desde `telemetria/sesiones/` | ⬜ |
| 0.9 | Ecosistema externo (GitHub, foros) | ✅ [INVESTIGACION-ECOSISTEMA.md](INVESTIGACION-ECOSISTEMA.md) |

**Criterio de salida:** decisiones Q1–Q4 tomadas; contrato revisado. Ver [RESUMEN.md](RESUMEN.md).

---

## Fase 1 — API mínima (modo CSV, sin memoria) ✅

Objetivo: `curl http://127.0.0.1:8765/v1/sample` devuelve última fila del CSV del juego **sin abrir nuevo código CE en el principal**.

| # | Tarea | Estado |
|---|-------|--------|
| 1.1 | `pyproject.toml` + FastAPI + uvicorn | ✅ |
| 1.2 | `GET /v1/health` | ✅ |
| 1.3 | `GET /v1/status` (csv path, file mtime, game inferido) | ✅ |
| 1.4 | `GET /v1/sample` → `ce_sample_v1` | ✅ |
| 1.5 | Parser CSV alineado con `CSV_HEADER` actual | ✅ |
| 1.6 | Mapeo `throttle` viejo → documentar si falta `throttle_input` | ✅ README + `sample.py` |
| 1.7 | Tests unitarios parser (fixture CSV) | ✅ |
| 1.8 | README con comandos `curl` | ✅ |
| 1.9 | `fase1_comprobar.bat` — checklist antes de Fase 2 | ✅ |

**Criterio de salida:** prueba manual con `telemetria_ce_log.csv` — ✅ Bandit, 942 filas (jul 2026).

---

## Primera prueba (Fase 1) — ejecutada

```powershell
cd snowrunner-telemetry-api
pip install -e ".[dev]"
python -m snowrunner_telemetry_api

# Otra terminal
Invoke-RestMethod http://127.0.0.1:8765/v1/health
Invoke-RestMethod http://127.0.0.1:8765/v1/status
Invoke-RestMethod http://127.0.0.1:8765/v1/sample
```

**Éxito:** JSON con `vehicle_id`, `speed_kmh`, `schema_version`; coherente con última línea del CSV.

---

## Qué no hacer antes de Fase 2

- No crear el proyecto C# del agente hasta cerrar 0.8 (fixtures JSON) si se usan en tests de contrato.
- No cambiar `importar_ce_csv.py` en el principal.
- No publicar API en LAN sin autenticación.
- No duplicar `comparar_telemetria` en este repo.

---

## Fase 2 — Agente nativo C# (memoria)

Proyecto: `agent/` → `snowrunner-telemetry-agent` (.NET 8, win-x64).

**Estado (jul 2026):** Fases **2.0** y **2.1** cerradas. **Pausa** antes de **2.2** — se retoma más adelante tras recopilar más datos en juego (offsets Havok, combustible en vivo). Fases 2.3–2.8 y Fase 3+ quedan en cola; no bloquean el uso actual del dashboard + agente en modo spike.

| # | Tarea | Estado |
|---|-------|--------|
| 2.0 | Scaffold `agent/SnowrunnerTelemetryAgent.csproj` + P/Invoke kernel32 | ✅ |
| 2.1 | Spike: `OpenProcess` + `read_active_sample` mínimo (speed, vehicle_id, throttle) | ✅ |
| 2.1.1 | `fase2_comprobar.bat` — build, offsets, WinMM; probe en vivo si hay juego | ✅ |
| 2.1.2 | Dashboard GUI (`fuel_pct`, `speed_kmh`, fuente agente/API) | ✅ (adelanto; no sustituye 2.4) |
| 2.2 | Port lecturas batched Havok (rigid body, ruedas, drive) desde `memoria_havok.py` | ⏸ **pausado** — ver [§2.2 pendiente](#fase-22--pendiente-recopilación-de-datos) |
| 2.3 | Cargar `offsets_referencia.json`; `throttle_resolver` portado | 🟡 parcial (en 2.1; falta paridad Python + env) |
| 2.4 | Loop muestreo + `POST /internal/ingest` → API buffer | ⬜ |
| 2.5 | `GET /v1/status` con `probe_ok`, `agent_version`, `throttle_spec` | ⬜ |
| 2.6 | Comparar muestra API vs `grabar_ce.py --probe` (ε en speed, vehicle_id, throttle_input) | ⬜ |
| 2.7 | `offsets_build` + `game_exe_version` (hash o FileVersion) en `/v1/status` | ⬜ |
| 2.8 | Checklist post-patch documentado + script `post_patch_comprobar` (probe + comparación) | ⬜ |

**Criterio de salida Fase 2 completa:** agente C# estable a 10 Hz; muestras indistinguibles del Python legacy en campos obligatorios (tarea 2.6).

### Fase 2.0 — scaffold ✅

| Entregable | Ubicación |
|------------|-----------|
| Proyecto `net8.0-windows` win-x64 | `agent/SnowrunnerTelemetryAgent.csproj` |
| P/Invoke `OpenProcess`, `ReadProcessMemory`, `CloseHandle` | `agent/Native/Kernel32.cs` |
| `VirtualQueryEx` (cache regiones válidas) | **Fase 2.2** — aún no en agente |
| `EnumProcessModulesEx`, `GetModuleBaseNameW` | `agent/Native/Psapi.cs` |
| RAII handle al proceso del juego | `agent/Memory/GameProcess.cs` |
| Lecturas tipadas + base del módulo PE | `agent/Memory/ProcessMemoryReader.cs` |
| Localizar PID `SnowRunner.exe` | `agent/Platform/SnowRunnerLocator.cs` |
| Launcher | `run_agent.bat` |

**Criterio 2.0:** `dotnet build` sin errores; con juego abierto, `OpenProcess` + lectura de memoria del módulo (sustituido por probe 2.1).

### Fase 2.1 — spike `read_active_sample` ✅

| Entregable | Ubicación |
|------------|-----------|
| Cadena Havok → vehículo activo, velocidad, `vehicle_id` | `agent/Havok/ActiveSampleReader.cs` |
| Throttle en memoria (per_vehicle, cache, auto_probe) | `agent/Havok/ThrottleResolver.cs` |
| Carga JSON de offsets | `agent/Config/OffsetsReference.cs`, `agent/data/offsets_referencia.json` |
| Pedal físico WinMM (eje RZ; juego abierto) | `agent/Input/WinMmJoystickReader.cs` |
| Merge memoria + hardware | `agent/Input/PhysicalInputReader.cs`, `ThrottleInputMerger.cs` |
| Salida JSON, `--loop`, diagnóstico | `agent/Program.cs` |
| Checklist | `fase2_comprobar.bat` |

**Criterio 2.1:** con SnowRunner en mapa y camión cargado, `.\run_agent.bat` → `probe_ok: true`, `vehicle_id` tipo `s_*`, `speed_kmh` coherente; `throttle_input` desde winmm (volante) o memoria Havok.

```powershell
.\fase2_comprobar.bat          # sin juego: build + offsets + WinMM
.\run_agent.bat                # una muestra (juego abierto)
.\run_agent.bat --loop         # poll continuo
```

**Nota:** parte de 2.3 (offsets + resolver) se adelantó en 2.1; la tarea 2.3 sigue abierta hasta paridad con Python y variables de entorno documentadas.

### Fase 2.2 — pendiente (recopilación de datos)

**Objetivo de código:** portar lecturas **batched** de `memoria_havok.py` — rigid body, ruedas, drive, terreno por rueda — no solo el spike mínimo de 2.1.

**Por qué pausa:** hace falta cerrar offsets de **ruedas/terreno** antes de portar el bloque batched completo. Combustible cerrado con `ce_fuel_hud` (ver abajo).

| Dato | Estado jul 2026 | Herramienta |
|------|-----------------|-------------|
| `speed_kmh`, `vehicle_id`, throttle | ✅ spike 2.1 | `.\run_agent.bat`, `fase2_comprobar.bat` |
| Combustible HUD en vivo | ✅ `ce_fuel_hud` | `.\run_agent.bat --fuel-debug` → `fuel_source=ce_fuel_hud`; ver [§11.5](INVESTIGACION-ECOSISTEMA.md#115-ce-pointerscan-combustible-usuario-jul-2026) |
| Ruedas / `terrain_kind` / drive batched | ⬜ sin portar | referencia `memoria_havok.py` en principal |

**Leads combustible archivados** (no seguir; solo fallback/diagnóstico en `FuelReader` si `ce_fuel_hud` rompe tras patch): `addon+868` + `veh+728` (snapshot estático ~199 L), `addon+258`, probes consume/repostaje (`130→05C`, `128→040`), lead FindMuck `addon+568`. Siguen visibles en `--fuel-debug` / `--fuel-diff`.

**Al retomar 2.2:**

1. Smoke test combustible: `fuel_source=ce_fuel_hud` y HUD ±2 L (consumo + repostaje); si falla tras patch → [mantenimiento post-patch](#mantenimiento-tras-patch-del-juego-continuo-no-bloquea-fase-3).
2. Inventariar en Python qué funciones de `memoria_havok.py` entran en el primer batch (rigid body + wheels mínimo).
3. Implementar `FieldReader` / lecturas por bloque en C# (mismo patrón batched que Python).
4. Ampliar muestra JSON del agente con columnas alineadas a `CSV_HEADER` (subset acordado en [CONTRATO-DATOS.md](CONTRATO-DATOS.md)).
5. Comparar con `grabar_ce.py` (precursor de tarea 2.6).

**Criterio de salida 2.2:** lecturas batched C# (rigid body + ruedas mínimo) alineadas con `memoria_havok.py`; `VirtualQueryEx` en cache de regiones; muestra ampliada sin regresión en `probe_ok` del spike 2.1. Combustible ya cubierto por `ce_fuel_hud` (no reabrir leads archivados salvo rotura de cadena).

**Mientras tanto (sin bloquear):** dashboard `--source agent`, documentación [INVESTIGACION.md §3 H](INVESTIGACION.md#h-script-o-mod-que-exponga--envíe-datos--es-posible), limpieza de código legacy.

### Mantenimiento tras patch del juego (continuo, no bloquea Fase 3)

No es una fase numerada aparte: es **trabajo esporádico** cada vez que Steam actualiza SnowRunner y rompe offsets Havok. La API **no descubre offsets sola** — solo reporta si están bien (`probe_ok`, `offsets_build`). El arreglo vive en `snowrunner real`.

| Tipo | Síntoma | Dónde se arregla |
|------|---------|------------------|
| **Patch del juego** | `probe_ok=false`, speed/vehicle_id absurdos, singletons rotos | CE + `offsets_referencia.json` en el principal |
| **Calibración por camión** | `throttle_input` pegado (~0.42), gas on/off igual | `drive_cal`, `throttle_resolver`, `calibracion.json` |

**Checklist tras un update de Steam** (ejecutar en el proyecto principal; validar desde esta API en Fase 2+):

1. Abrir SnowRunner parado en garaje con un camión conocido (ej. Bandit).
2. `grabar_ce.py --probe` → si falla, re-encontrar singletons con Cheat Engine.
3. Actualizar `cheat_engine/offsets_referencia.json` (nuevo `offsets_build`, ej. `ago-2026`).
4. Re-ejecutar `--probe` hasta `probe_ok` y campos coherentes (speed ≈ 0, `vehicle_id` correcto).
5. Copiar/sincronizar `offsets_referencia.json` al agente C# (`SNOWRUNNER_OFFSETS_PATH`).
6. Comparar agente vs legacy: tarea **2.6** (ε en speed, vehicle_id, throttle_input).
7. Si `throttle_input` mal solo en un camión → calibrar ese vehículo (`drive_cal`), no tocar offsets globales.
8. `GET /v1/status` debe mostrar `probe_ok: true`, `offsets_build` actualizado, `game_exe_version` distinto al anterior si el `.exe` cambió.

**Herramientas de referencia** (no sustituyen vuestro pipeline): [SnowRunner_Noclip mappings.md](https://github.com/FindMuck/SnowRunner_Noclip/blob/main/mappings.md), [CE_RTTI_Reverse_Lookup](https://github.com/FindMuck/CE_RTTI_Reverse_Lookup). Ver [INVESTIGACION-ECOSISTEMA.md](INVESTIGACION-ECOSISTEMA.md).

**Criterio de “offsets OK”:** `probe_ok=true` en `/v1/status` **y** muestra del agente ≈ `grabar_ce.py --probe` en campos obligatorios.

---

## Fase 3 — Sesiones y cliente principal

*En cola — retomar tras cerrar o avanzar suficiente Fase 2 (mínimo 2.4 ingest + 2.6 paridad).*

| # | Tarea | Estado |
|---|-------|--------|
| 3.1 | `POST /v1/sessions/start`, `/end` + `GET /v1/sessions/{id}` | ⬜ |
| 3.2 | `telemetry_client.py` en `snowrunner real` | ⬜ |
| 3.3 | Flag en `grabar_telemetria.bat`: `--via-api` | ⬜ |
| 3.4 | Import + compare sin CSV intermedio | ⬜ |

---

## Fase 4 — Stream (opcional)

*En cola — tras Fase 3 o si hace falta monitor de baja latencia.*

| # | Tarea | Estado |
|---|-------|--------|
| 4.1 | WebSocket `/v1/stream` | ⬜ |
| 4.2 | Adaptar `pedal_monitor` a API | ⬜ |

---

Ver también [RESUMEN.md](RESUMEN.md) — síntesis de todo el trabajo realizado.
