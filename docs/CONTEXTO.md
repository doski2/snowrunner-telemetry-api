# Contexto — necesidad de la API

## Situación actual (`snowrunner real`)

El flujo de telemetría hoy es **monolítico**:

```
SnowRunner.exe
    → memoria_havok.py (ReadProcessMemory)
    → telemetria_ce_log.csv
    → importar_ce_csv.py
    → telemetria/sesiones/<vehículo>/ce_*.json
    → comparar_telemetria.py / indexar_sesion.py
    → datos/indices/calibracion.json
    → sim/core.py + camiones/*/simulador.py
```

**Fuentes de verdad del contrato de datos** (proyecto principal):

- `cheat_engine/memoria_havok.py` — columnas CSV (`CSV_HEADER`)
- `telemetria.py` — `TelemetrySample`, `SessionMeta`, `TelemetrySession`
- `importar_ce_csv.py` — CSV → JSON
- `datos/session_context.py` — metadatos obligatorios
- `camiones/registry.py` — `vehicle_id` ↔ `s_*` del juego

## Problemas que motivan la API

### 1. Acoplamiento físico al juego

- Lectura de memoria requiere **mismo PC**, **SnowRunner corriendo**, **permisos de proceso**.
- Scripts de análisis (`comparar`, `indexar`, `consultar_base`) viven junto al lector CE.
- No se puede grabar en un PC y analizar en otro sin copiar CSV a mano.

### 2. Frontera de datos poco clara

- El CSV mezcla **adquisición** (Havok) con **semántica de negocio** (protocolo F1/F2, MAE).
- Grabaciones antiguas tienen columnas distintas (`throttle` vs `throttle_input` / `throttle_motor`).
- No hay versión de esquema ni endpoint de “última muestra”.

### 3. SnowRunner no ofrece telemetría oficial

Cita del propio `telemetria.py`:

> SnowRunner no publica telemetría (SimHub, API, UDP).

Todo depende de **ingeniería inversa** (offsets, singletons `TRUCK_CONTROL` / `DRIVE_LOGIC`). Eso debe vivir en un **módulo de adquisición** estable, no repartido entre grabación y sim.

### 4. Escalabilidad del flujo de calibración

- Varios camiones (`ck1500`, `bandit`, `t813`…) con offsets **por vehículo** (`throttle_resolver`, `per_vehicle`).
- El proyecto principal debe **consumir muestras ya normalizadas**, no redescubrir punteros en cada script.

## Qué debe hacer la API (alcance)

| Sí | No |
|----|-----|
| Exponer **muestras en vivo** (stream o poll) | Aplicar parches `.pak` |
| Exponer **sesiones** (JSON alineado con `TelemetrySession`) | Calcular MAE / comparar con sim |
| Informar **estado** (juego detectado, vehículo activo, offsets OK) | Gestionar `datos/catalogo/` |
| Opcional: archivar CSV/JSON crudo | Sustituir `consultar_base.py` |

## Qué sigue haciendo el proyecto principal

- `camiones/`, `sim/`, `apply_mod.py`, `patches.py`
- `comparar_telemetria.py`, `indexar_sesion.py`, `datos/build_indices.py`
- Protocolos F1/F2/F3, `PENDIENTES.md`, calibración por camión
- **Cliente** de la API: sustituir o complementar `grabar_ce.py --live` por `GET /samples` o webhook

## Beneficio esperado

1. **Un solo contrato** de muestra para CSV, API y JSON.
2. **Agente Windows** (lector memoria) separado del **servidor de análisis** (puede ser el mismo PC al inicio).
3. Posibilidad futura: grabar siempre igual aunque cambien offsets internos (la API abstrae `tc+0E8` vs `tc+0F8`).
4. Tests de la API con **fixtures JSON** sin abrir el juego.

## Enlace entre repos

```
snowrunner-telemetry-api/     snowrunner real/
  docs/CONTRATO-DATOS.md  ←→  telemetria.py, memoria_havok.CSV_HEADER
  (futuro) OpenAPI          ←→  importar_ce_csv.py (cliente HTTP)
```

Ver [INVESTIGACION.md](INVESTIGACION.md) para cómo llegar ahí sin implementar demasiado pronto.
