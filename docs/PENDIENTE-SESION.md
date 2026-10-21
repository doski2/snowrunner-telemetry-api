# Traspaso de sesión — qué funciona, qué falta descubrir

Última actualización: 2026-10-21. Objetivo del proyecto: **medir el comportamiento real en el juego
para ajustar el mod realista** (`C:\Users\doski\snowrunner real`, parches XML → `initial.pak`).
El flujo CE/API del mod está archivado allí; este repo es el que mide.

## Estado en una línea

El agente C# lee velocidad, combustible, terreno por rueda y **acelerador del juego**, y hay
grabación/análisis por camión y terreno. **Offsets verificados el 2026-10-21 tras la actualización
de
ese día: siguen válidos (`probe_ok`).

## Primer paso en la próxima sesión (obligatorio)

1. Abrir SnowRunner con un camión en mapa (parado, ralentí).
2. `.\run_agent.bat --memory-only` → debe acabar con `[OK] probe_ok`.
3. Si falla (`exit 3`, "sin vehiculo activo o cadena Havok rota"):
   - `.\run_agent.bat --find-singletons --id=<vehicle_id del camión>` (ej. `s_krs_58_bandit`).

     Devuelve `singleton exe+XXXX -> +0x20 -> vehicle ... id@+0xD10`. El `+0x20` y el `id@+0xD10`
     son los valores esperados; ignorar hits con `id@` desalineado (p. ej. `+0xC29`).

   - Desplazamiento = nuevo `DRIVE_LOGIC` − `0x2A92E28`. Aplicarlo a `TRUCK_CONTROL`

     (`0x2A92E38`), `DRIVE_LOGIC` y `fuel_pointerscan.ce_fuel_hud.module_offset` (`0x2A92E40`) en
     [agent/data/offsets_referencia.json](../agent/data/offsets_referencia.json). Actualizar
     `source` y `game_version`. Respetar los saltos de línea del fichero (CRLF/LF) al editarlo.

   - Repetir hasta `probe_ok`. El layout interno del vehículo no cambió en sep-2026.
4. Comprobar el acelerador: `.\run_agent.bat --throttle-find --duration=40` pisando y soltando a

   fondo. Debe volver a salir `veh+68->+44` con |r| ≈ 1 y rango [−1, 0]. Si cambia, actualizar
   `drive_runtime.throttle_game` en el JSON de offsets.

5. Validar que `throttle_game` (0–1) sube con el pedal y que la aceleración crece con el gas.

## Qué funciona (comprobado con el juego, build sep-2026)

| Dato                     | Campo en la muestra                            | Notas                                                                      |
| ------------------------ | ---------------------------------------------- | -------------------------------------------------------------------------- |
| Velocidad, vehículo      | `speed_kmh`, `vehicle_id`                      | `vehicle_id` inline en `vehicle+0xD10`                                     |
| Combustible              | `fuel_liters`, `fuel_cap_liters`, `fuel_pct`   | Capacidad leída de memoria (`field+0x8`); validado con el Fleetstar vs HUD |
| Terreno por rueda        | `terrain_kind`, `wheel_grip`, `surface_avg`, … | Modo saturado para el Bandit                                               |
| **Acelerador del juego** | `throttle_game` (0–1)                          | `-[[vehicle+0x68]+0x44]`; corr. 0,98 con el pedal                          |
| Reloj del agente         | `ts_ms`                                        | Más exacto que la hora de lectura en Python                                |
| **Posición**             | `pos` [x, y, z]                                | `rb+0x1A0`; distancia recorrida y altitud |
| **Orientación**          | `rot` (9 floats: 3 columnas)                   | `rb+0x170/0x180/0x190`, ortonormales; de aquí salen cabeceo y alabeo |
| **Velocidad angular**    | `ang_vel` [x, y, z]                            | `rb+0x240`; el eje Y da la guiñada → fuerza lateral |

**No fiables** (no usar): `throttle_input` / `throttle_motor` (offsets muertos tras el patch) y
`throttle_input_physical` (la conversión WinMM trata 0,35–0,75 como neutral).

## Herramientas del repo

| Comando                                                               | Para qué                                                                                                                                                                         |
| --------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `.\record_play.bat`                                                   | Grabar juego normal sin ventana: un NDJSON por camión en `data/sessions/`, con cabecera `_meta` (exe, pak, SHA1, offsets). Adelgaza el ralentí y reintenta si se cierra el juego |
| `run_dashboard.bat --source agent [--record ETIQUETA]` | Dashboard en vivo: velocidad, gas con sugerencia, combustible, terreno, inclinación, aceleración neta y consumo. Agente a 100 ms, repinta cada 150 ms; con `--record` graba cada muestra del agente |
| `python scripts/report_profiles.py [--vehicle ID] [--write-ideal]`    | Informe por camión y terreno; `--write-ideal` genera `data/ideal_throttle.json` para el dashboard                                                                                |
| `python scripts/analyze_session.py <fichero> [--target obj.json]`     | Métricas de una sesión: 0–20/40/60/80 km/h, vmax, consumo, terreno                                                                                                               |
| `python scripts/acceleration_test.py --label vanilla`                 | Medición guiada de aceleración a fondo                                                                                                                                           |
| `python scripts/extract_game_catalog.py`                              | Catálogo estático desde `initial.pak` → `data/game_catalog.json`                                                                                                                 |
| `.\run_agent.bat --find-singletons` / `--throttle-find`               | Reencontrar offsets tras un patch                                                                                                                                                |

Código nuevo: [analysis.py](../src/snowrunner_telemetry_api/analysis.py),
[autorecord.py](../src/snowrunner_telemetry_api/autorecord.py),
[dashboard/recorder.py](../src/snowrunner_telemetry_api/dashboard/recorder.py),
[dashboard/advice.py](../src/snowrunner_telemetry_api/dashboard/advice.py),
`agent/Program.FindSingletons.cs`, `agent/Program.ThrottleFind.cs`. Procedimiento de calibración:
[CALIBRACION.md](CALIBRACION.md). Tests: `python -m pytest` (64 pasan).

## Cálculos derivados (módulo `physics.py`)

Se calculan en vivo para el dashboard y en lote para el análisis (`analysis.enrich`), con funciones
puras y tests (`tests/test_physics.py`):

| Magnitud | Cómo se calcula | Para qué |
|----------|-----------------|----------|
| Eje delantero | Columna de `rot` más alineada con la velocidad al avanzar (≥ 25 muestras > 3 km/h) | Base de todo lo demás. **Columna 0, signo +** medido con el Scout 800 (alineación 0,997); se re-verifica con cada camión y se guarda como a priori en `data/forward_axis.json` |
| Cabeceo, alabeo, pendiente (%) | Del eje delantero y el eje «arriba» | Pendiente real, no estimada con `vel.y` |
| Aceleración medida | Derivada de la velocidad longitudinal en 0,5 s | — |
| **Aceleración neta** | medida + g·sen(cabeceo) | Lo que aporta el motor, independiente de la pendiente. Sustituye a la derivada simple en el «gas ideal» |
| Fuerza lateral (g) | v_long × velocidad de guiñada / g | Giros bruscos y vuelcos |
| Distancia | Suma de desplazamientos de `pos` (ignora saltos > 50 m) | Consumo por km |
| Consumo L/h y L/100 km | Caída de `fuel_liters` en 20 s | Eficiencia según gas y terreno |

El dashboard muestra una tercera fila con inclinación, aceleración neta y consumo. Los informes
(`report_profiles.py`) incluyen pendiente p90 y fuerza lateral p90 por terreno.

**Pendiente de validar:** la detección automática del eje se probó solo con 5 muestras en
movimiento (vmax 9 km/h). Hace falta una conducción de ≥ 45 s, con cuestas y algún giro, para
comprobar el signo del cabeceo y del alabeo y la coherencia entre el cabeceo de `rot` y el ángulo de
la velocidad. El consumo de ~88 L/h del Scout al 68 % de gas es real (el depósito de 72 L dura menos
de una hora), no un artefacto: `fuel_liters` baja de forma continua.

## Pendiente de descubrir en memoria

Técnica general (la que funcionó con el acelerador): `--throttle-find` correlaciona cada f32 del
vehículo y de los objetos a los que apunta con una señal conocida mientras el usuario actúa.
Generalizarlo a "correlacionar con una señal X" sería una refactorización útil.

| Prioridad   | Dato                              | Por qué                                                                                                                         | Cómo encontrarlo                                                                               |
| ----------- | --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| 1           | **Giro de cada rueda (patinaje)** | Mide la tracción real: giro de rueda vs velocidad del suelo. Sin él, el "gas ideal" no distingue gas útil de gas que patina     | Correlación con la velocidad en las ruedas del array `vehicle+0x200` (inicio) / `+0x208` (fin) |
| 2           | **Marcha actual y reductora (L)** | Cambian la aceleración y el consumo                                                                                             | Observar el agente al cambiar marcha / pulsar L                                                |
| 3           | **Bloqueo de diferencial y AWD**  | Afecta a tracción en barro                                                                                                      | Pulsar y soltar con el agente observando                                                       |
| 4           | **RPM del motor**                 | Ver en qué zona de la curva de torque se trabaja (lo que ajusta el mod). Candidato antiguo `vehicle+0x114` probablemente muerto | Correlación con velocidad y marcha                                                             |
| 5           | **Remolque / carga / masa total** | Cambia la masa efectiva                                                                                                         | Offsets `attach_manager +0x78`, `cargo_manager +0x1E8` ya conocidos, sin interpretar           |
| 6           | **Daño de motor y ruedas**        | Sesga las medidas de potencia                                                                                                   | Difícil; cambia solo al dañarse                                                                |
| 7           | **Freno, volante, freno de mano** | Separar frenadas y giros de aceleraciones                                                                                       | Igual que el acelerador, con el eje del volante                                                |
| ✅          | ~~Posición y orientación~~        | Hecho: `pos`, `rot`, `ang_vel` | Cuerpo rígido Havok |
| 8           | **Masa total del vehículo**       | Con masa y aceleración neta se estima la potencia a las ruedas (P = m·a·v) y se compara con el motor del XML | `rb+0xB8 → +0xA4` (masa inversa) **no vale**: el cuerpo principal pesa ~50 kg. Hay que sumar los cuerpos de la «isla de simulación» (`rb+0x128 → bodies+0x60`, nº en `+0x68`) |

Faltan banderas de calidad por fila (juego en pausa, saltos de `sample_seq`).

## Preguntas abiertas

- **Capacidad de combustible — resuelto (2026-10-21), falta confirmar en otro camión.** Antes

  `fuel_cap_liters` era la constante 210 (`FuelDefaultCapacityLiters`) y `fuel_pct` salía mal para
  camiones de otra capacidad; además la validación `litros ≤ capacidad+15` habría descartado
  lecturas válidas en depósitos grandes. Ahora la capacidad se lee de memoria: f32 en
  `campo_de_litros + 0x8` (`capacity_delta` en `ce_fuel_hud`). Comprobado con el Fleetstar:
  HUD 156/240 L → el agente da `fuel_liters` 155,1, `fuel_cap_liters` 240, `fuel_pct` 64,6.
  El usuario confirmó que nivel actual y total coinciden con el HUD (2026-10-21).
  **Pendiente:** verificarlo con otro camión (p. ej. Bandit: 150 L en XML, 135 con el mod aplicado).
  La constante 210 solo queda como último recurso y marca la fuente `ce_fuel_hud+cap_default`.

- **Resolución de `fuel_liters`** en ralentí: en 24 s no se movió. Grabar varios minutos.
- **Pak del mod no aplicado.** El de Steam es vanilla. Para comparar mod vs vanilla hay que

  ejecutar `apply_mod.py` (en `snowrunner real`) y repetir; la cabecera `_meta` de cada sesión
  registra el SHA1 del pak para separarlas.

- **Calidad del clasificador de barro**: F2 del mod depende de `terrain_kind`.
- La aceleración depende de pendiente, marcha, carga y daño; el "gas ideal" actual significa

  "a partir de aquí más gas no sube la aceleración", no un óptimo físico.

## Plan de uso para ajustar el mod

1. Verificar offsets (arriba).
2. Grabar horas de juego normal con `record_play.bat`, camión a camión.
3. `report_profiles.py --write-ideal` y revisar velocidades p50/p90, uso de gas a fondo y L/h por

   terreno.

4. Comparar con los objetivos de `camiones/<id>/FASES.md` y su simulador

   (`python -m camiones.<id>.simulador`) y ajustar `patches.py`.

5. `apply_mod.py`, repetir la grabación y comparar (sesiones separadas por SHA1 del pak).

## Detalles prácticos

- **Nada está commiteado.** Hay muchos cambios sin commit, incluidos anteriores a esta sesión

  (`WheelTerrainReader.cs`, `offsets_referencia.json`, `terrain_classifier.py`, …).

- `data/sessions/`, `data/accel_*.json` y `data/game_catalog.json` están en `.gitignore`.
- Cerrar el dashboard con la X; si se mata a la fuerza queda un proceso `dotnet` huérfano del

  agente (hay que cerrarlo a mano).

- El dashboard fuerza `--memory-only` para el agente; `throttle_game` no necesita el pedal físico.
- Las rutas del juego se pueden cambiar con `SNOWRUNNER_GAME_DIR`.
