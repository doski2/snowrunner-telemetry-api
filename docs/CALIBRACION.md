# Calibración del mod con datos medidos

Objetivo de la API: **medir el comportamiento real en el juego** y usarlo para ajustar los parches
XML de `snowrunner real` (`camiones/<id>/patches.py`), en vez de validar solo a ojo.

## Flujo

```text
```

## Procedimiento por fase del mod

Mismas condiciones que `camiones/<id>/FASES.md`. Una sesión por fase y por variante (`vanilla`,
`mod`).

| Fase       | Cómo grabar                                                   | Qué mirar en el análisis                   |
| ---------- | ------------------------------------------------------------- | ------------------------------------------ |
| F1 asfalto | `--record bandit_f1_vanilla`, parado en recta, WOT ~60 s      | `acceleration.t_to_kmh`, `vmax_kmh`        |
| F2 barro   | `--record bandit_f2_vanilla`, marcha L, gas sostenido 30–60 s | `terrain.mud_speed_mean_kmh` / `max`       |
| Consumo    | cualquiera con tramo parado y en marcha                       | `fuel.idle.l_per_h`, `fuel.moving.l_per_h` |

Comparar con el simulador del mod (`python -m camiones.<id>.simulador`) usando `--target`:

```json
```

## Comprobaciones antes de medir

1. `.\run_agent.bat` → `[OK] probe_ok`. Si falla tras un patch del juego:

   `.\run_agent.bat --find-singletons --id=<vehicle_id>` con ese camión activo, y aplicar el
   desplazamiento a `TRUCK_CONTROL`, `DRIVE_LOGIC` y `ce_fuel_hud` en
   `agent/data/offsets_referencia.json`.

2. Saber qué `initial.pak` está instalado: el de Steam es vanilla hasta ejecutar `apply_mod.py`.

## Limitaciones conocidas

- `fuel_cap_liters` se lee de memoria junto al campo de litros; si la fuente acaba en `+cap_default`

  es la constante 210 y `fuel_pct` no es fiable. Validado solo con el Fleetstar (240 L).

- La resolución de `fuel_liters` puede ser demasiado gruesa para consumos en ralentí en sesiones

  cortas; grabar varios minutos.

- El análisis de barro depende del clasificador de terreno (`terrain_kind`).

Traspaso entre sesiones: [PENDIENTE-SESION.md](PENDIENTE-SESION.md).
