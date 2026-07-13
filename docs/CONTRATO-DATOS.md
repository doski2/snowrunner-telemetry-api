# Contrato de datos — API ↔ proyecto principal

Este documento fija **qué debe enviar la API** para que `snowrunner real` pueda importar y comparar sin cambios grandes.

**Fuente de verdad:** archivos en `../snowrunner real/` (ruta relativa desde este repo hermano).

---

## Versiones de esquema

| `schema_version` | Estado    | Notas                                             |
|------------------|-----------|---------------------------------------------------|
| `ce_sample_v1`   | propuesto | Una muestra Havok normalizada                     |
| `ce_session_v1`  | propuesto | Sesión completa compatible con `TelemetrySession` |

Cada payload JSON incluye `"schema_version": "ce_sample_v1"`.

---

## Muestra (`ce_sample_v1`)

Alineada con `memoria_havok.CSV_HEADER` y enriquecimiento `enrich_drive_fields`.

### Campos obligatorios

| Campo          | Tipo   | Ejemplo                  | Uso en principal              |
|----------------|--------|--------------------------|-------------------------------|
| `t_s`          | float  | `12.34`                  | Tiempo sesión                 |
| `speed_kmh`    | float  | `28.5`                   | MAE, tramos                   |
| `vehicle_id`   | string | `s_krs_58_bandit`        | `registry.vehicle_id_from_ce` |
| `terrain_kind` | string | `hard` / `mud` / `mixed` | Segmentación compare          |
| `chain`        | string | `TRUCK_CONTROL`          | Diagnóstico                   |

### Campos recomendados (terreno / carga)

| Campo             | Tipo   | Notas               |
|-------------------|--------|---------------------|
| `wheel_grip`      | float  |                     |
| `surface_avg`     | float  |                     |
| `contact_avg`     | float  |                     |
| `mud_grade`       | int    |                     |
| `mud_grade_label` | string |                     |
| `load_hint`       | string | `vacio` / `cargado` |
| `total_mass_kg`   | float  | Havok               |
| `payload_kg`      | float  |                     |
| `map_name`        | string |                     |
| `level_id`        | string |                     |

### Campos drive (gas / motor)

| Campo                   | Tipo       | Notas                                      |
|-------------------------|------------|--------------------------------------------|
| `throttle_input`        | float 0..1 | **Input jugador** (TRUCK_CONTROL)          |
| `throttle_motor`        | float 0..1 | Demanda motor (`vehicle+760`)              |
| `throttle`              | float      | Legacy = `throttle_input` o fallback motor |
| `engine_rpm`            | float      |                                            |
| `throttle_input_src`    | string     | `per_vehicle` / `auto_probe` / `global`    |
| `throttle_input_base`   | string     | ej. `tc+0F8`                               |
| `throttle_input_offset` | string     | ej. `+0x0C8`                               |

**Regla:** la API no debe emitir solo `throttle` sin `throttle_input` cuando el resolver tenga spec válido.

### Campos opcionales

Posición, yaw, fuel, diff/awd/low, trailer, etc. — mismos nombres que CSV actual.

### Ejemplo mínimo

```json
{
  "schema_version": "ce_sample_v1",
  "t_s": 3.61,
  "speed_kmh": 5.66,
  "vehicle_id": "s_krs_58_bandit",
  "terrain_kind": "hard",
  "chain": "TRUCK_CONTROL",
  "throttle_input": 0.85,
  "throttle_motor": 1.0,
  "throttle": 0.85,
  "engine_rpm": 1200,
  "map_name": "Black River",
  "level_id": "level_us_01_01"
}
```

---

## Sesión (`ce_session_v1`)

Compatible con `telemetria.py`:

```python
@dataclass
class TelemetrySession:
    meta: SessionMeta
    samples: list[TelemetrySample]
```

### `meta` mínimo

| Campo             | Obligatorio                         |
|-------------------|-------------------------------------|
| `vehicle_id`      | sí (mod id: `bandit`, `ck1500`)     |
| `protocol_id`     | recomendado                         |
| `map_name`        | sí                                  |
| `duration_s`      | sí                                  |
| `session_context` | sí (ver `datos/session_context.py`) |

### `session_context` obligatorio

| Campo           | Ejemplo                        |
|-----------------|--------------------------------|
| `build_juego`   | Steam jun-2026                 |
| `mod_commit`    | git hash                       |
| `map`           | Black River                    |
| `location_note` | partida libre                  |
| `baseline_tag`  | play_free_v1                   |
| `capture_tool`  | `snowrunner-telemetry-api/0.1` |

### Muestras en sesión

Cada elemento de `samples[]` puede ser:

- objeto `ce_sample_v1` completo, o
- formato actual `TelemetrySample` del principal (`speed_kmh`, `note` con kv, etc.)

**Estrategia de transición:** la API emite `ce_sample_v1`; el cliente principal convierte a `TelemetrySample` igual que `importar_ce_csv.csv_row_to_sample`.

---

## Estado del sistema (`GET /v1/status`)

```json
{
  "schema_version": "status_v1",
  "api_ok": true,
  "game_running": true,
  "pid": 24104,
  "vehicle_ce_id": "s_chevrolet_ck1500",
  "vehicle_mod_id": "ck1500",
  "probe_ok": true,
  "agent_mode": "csv",
  "offsets_build": "jun-2026",
  "throttle_input_ok": true,
  "throttle_spec": {
    "base": "tc+0F8",
    "offset": "+0x0C8",
    "kind": "u8",
    "source": "per_vehicle"
  },
  "map_name": "Black River",
  "samples_buffered": 842,
  "last_sample_t_s": 1265.4
}
```

---

## Mapeo vehículo

Desde `camiones/registry.py` (principal):

| `vehicle_id` CE      | mod id      |
|----------------------|-------------|
| `s_chevrolet_ck1500` | `ck1500`    |
| `s_krs_58_bandit`    | `bandit`    |
| `s_fleetstar_f2070a` | `fleetstar` |
| `s_khan_39_marshall` | `marshall`  |
| `s_tatra_t813`       | `t813`      |
| `s_gmc_9500`         | `mh9500`    |

La API puede incluir `vehicle_mod_id` resuelto para evitar duplicar lógica en el cliente.

---

## Calidad — reglas heredadas del principal

1. Sesión inválida si >50 % muestras sin `terrain_kind` (`datos/README.md`).
2. Preflight gas: con vehículo parado, `throttle_input` ≤ 0.15 (`calibrar_drive.preflight_check`).
3. Archivar CSV crudo en `datos/raw/ce_csv/` es responsabilidad del **cliente** principal, no de la API.

---

## Archivos de referencia (principal)

```
snowrunner real/
  cheat_engine/memoria_havok.py      # CSV_HEADER, read_active_sample
  telemetria.py                      # TelemetrySession, TEST_PROTOCOLS
  importar_ce_csv.py                 # csv → session
  datos/session_context.py
  camiones/registry.py
  cheat_engine/offsets_referencia.json
```

---

## Cambios futuros en el contrato

- Añadir campo → incrementar versión (`ce_sample_v2`).
- La API y el principal declaran versiones soportadas en `/v1/status`.
- Tests de contrato en este repo con fixtures copiados de sesiones reales.
