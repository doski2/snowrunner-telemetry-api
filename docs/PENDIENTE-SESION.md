# Traspaso de sesión — qué funciona, qué falta

Última actualización: 2026-10-21 (noche). Objetivo del proyecto: **medir el comportamiento real en el juego para
ajustar el mod realista** (`C:\Users\doski\snowrunner real`, parches XML → `initial.pak`). El flujo CE/API del mod
está archivado allí; este repo es el que mide.

## Estado en una línea

El agente C# lee velocidad, combustible (directo), terreno por rueda, orientación, giro de ruedas y entradas del
conductor (gas, freno, volante). El dashboard graba solo y calcula pendiente, aceleración neta, patinaje y consumo. Hay
informes por camión, terreno y etiquetas de contexto. Falta **marcha, diferencial/AWD/reductora, RPM, masa y daño**, y
reunir sesiones con barridos de gas para que la eficiencia sea fiable.

## Primer paso en la próxima sesión (obligatorio)

El juego se actualizó el 2026-09-03 y otra vez el 2026-10-21 (`SnowRunner.exe` 46 808 616 B); los offsets siguieron
válidos en ambos casos, pero hay que comprobarlo siempre antes de fiarse de una lectura.

1. Abrir SnowRunner con un camión en mapa (parado, ralentí).
2. `.\run_agent.bat --memory-only` → debe acabar con `[OK] probe_ok`.
3. Si falla (`exit 3`, «sin vehiculo activo o cadena Havok rota»):
   - `.\run_agent.bat --find-singletons --id=<vehicle_id del camión>` (ej. `s_krs_58_bandit`). Devuelve
     `singleton exe+XXXX -> +0x20 -> vehicle ... id@+0xD10`; ignorar hits con `id@` desalineado (p. ej. `+0xC29`).
   - Desplazamiento = nuevo `DRIVE_LOGIC` − `0x2A92E28`. Aplicarlo a `TRUCK_CONTROL` (`0x2A92E38`), `DRIVE_LOGIC` y
     `fuel_pointerscan.ce_fuel_hud.module_offset` (`0x2A92E40`) en
     [agent/data/offsets_referencia.json](../agent/data/offsets_referencia.json). Actualizar `source` y `game_version`.
     Respetar los saltos de línea del fichero (CRLF/LF).
   - Repetir hasta `probe_ok`. El layout interno del vehículo no ha cambiado.
4. Comprobar las entradas del conductor: `.\run_agent.bat --throttle-find --duration=40` pisando y soltando el gas a fondo.
   Debe salir `veh+68->+44` con |r| ≈ 1. Si cambia, actualizar `drive_runtime.throttle_game`.
5. Abrir el dashboard (`run_dashboard.bat --source agent`): la tarjeta *Camión* debe mostrar las etiquetas y *Grabación*
   la cobertura. Los datos de `fuel_liters_raw` deben coincidir con el HUD.

## Qué funciona (comprobado con el juego, build oct-2026)

| Dato | Campo en la muestra | Notas |
| ---- | ------------------- | ----- |
| Velocidad, vehículo | `speed_kmh`, `vehicle_id` | `vehicle_id` inline en `vehicle+0xD10` |
| Reloj del agente | `ts_ms` | Más exacto que la hora de lectura en Python |
| **Combustible directo** | `fuel_liters_raw`, `fuel_cap_liters`, `fuel_pct` | Cadena `ce_fuel_hud`; capacidad leída de memoria (`field+0x8`), validada en **4 camiones** (Fleetstar 240, Scout 800 72, Tatra T813 380, Bandit 150 L) y coincidente con el HUD. Es continuo (escalón ≈ 0,01 L por muestra). **Para medir consumo usar solo `fuel_liters_raw`** |
| Combustible interpolado | `fuel_liters` | Lo modela `FuelSessionTracker` (burn = 0,018 + carga·0,075 L/s); sirve para mostrar el nivel, **no para analizar consumo** |
| Terreno por rueda | `terrain_kind`, `wheel_grip`, `surface_avg`, … | Modo saturado para el Bandit. Sospechoso: parpadea (4–7 cambios/min) y etiqueta «ice» donde no debería |
| **Gas** | `throttle_game` (0–1) | `[vehicle+0x68]+0x44`, signo invertido; corr. 0,98 con el pedal |
| Freno | `brake_game` (0–1) | Mismo campo que el gas (positivo = freno/marcha atrás, r = 0,90 con el eje U). **No se ha usado nunca** (ver abajo) |
| Volante | `steer_game` (−1…1) | `[vehicle+0x68]+0x40`, r = −0,998 con el eje X. Consistente entre camiones (ver «Sesiones») |
| Posición | `pos` [x, y, z] | `rb+0x1A0` |
| Orientación | `rot` (9 floats, 3 columnas) | `rb+0x170/0x180/0x190`, ortonormales. **Eje delantero = columna 0** |
| Velocidad angular | `ang_vel` [x, y, z] | `rb+0x240`; el eje Y da la guiñada |
| Giro de ruedas | `w_omega` [rad/s por rueda] | `+0x2D0` en cada objeto rueda (`vehicle+0x200`); radio efectivo calibrado: Scout 0,44 m, Tatra 0,655 m |
| `w_speed` (sin uso) | `w_speed` | `+0x2DC` por rueda; correlaciona 0,98 con la velocidad pero con escala ≈ 0,3×: **significado sin entender, no usar** |

**No fiables:** `throttle_input` / `throttle_motor` (offsets muertos tras el patch) y `throttle_input_physical` (la
conversión WinMM trata 0,35–0,75 como neutral).

### Sobre el freno (aportación del usuario)

El freno prácticamente no se usa al jugar: **al soltar el acelerador el camión frena bastante** (freno motor / retención
automática), sobre todo cuesta arriba al maniobrar. Consecuencias: `brake_game` sale 0 en todas las sesiones y validarlo es
de **baja prioridad**; lo que sí importa medir es la **deceleración con gas = 0** según velocidad, pendiente y terreno
(en la primera prueba: −2,16 km/h/s con el gas suelto). Idea pendiente: informe de «freno motor» por situación.

## Herramientas del repo

| Comando | Para qué |
| ------- | -------- |
| `run_dashboard.bat --source agent` | Dashboard en vivo (velocidad, gas con sugerencia de gas ideal y eficiente, combustible, terreno, inclinación, aceleración neta + patinaje, consumo, cobertura). **Graba solo** (fila mínima, un fichero por camión en `data/sessions/`); `--no-record`, `--full-rows`, `--cap-seconds N`. Agente a 100 ms, repinta cada 150 ms |
| `.\record_play.bat` | Lo mismo sin ventana (prefijo `play_`). **No ejecutarlo a la vez que el dashboard**: cada uno lanza su propio agente |
| `python scripts/set_context.py carga=vacio diff=on` | Etiquetas de contexto (carga, neumáticos, diff…) que se graban en cada fila y agrupan los informes; se aplican en caliente. `--show`, `--unset`, `--clear` |
| `python scripts/report_profiles.py [--vehicle ID] [--efficiency] [--write-ideal] [--write-efficiency] [--rebuild-coverage]` | Informe por camión y terreno; `--efficiency` da L/100 km por tramo de gas con cobertura, confianza y patinaje; los `--write-*` generan las tablas que lee el dashboard |
| `python scripts/compact_sessions.py` | Comprime sesiones terminadas a `.ndjson.gz` (≈ 10× menos); los informes leen ambos formatos |
| `python scripts/analyze_session.py <fichero> [--target obj.json]` | Métricas de una sesión: 0–20/40/60/80 km/h, vmax, consumo, terreno |
| `python scripts/acceleration_test.py --label vanilla` | Medición guiada de aceleración a fondo |
| `python scripts/extract_game_catalog.py` | Catálogo estático desde `initial.pak` → `data/game_catalog.json` |
| `run_agent.bat --find-singletons [--id=…]` | Reencontrar los singletons tras un patch |
| `run_agent.bat --throttle-find --axis=x/y/z/r/u/v [--deep]` | Correlaciona la memoria con un eje del mando (en este mando: r = acelerador, x = volante, u = freno) |
| `run_agent.bat --wheel-find --duration=40` | Giro de ruedas: correlaciona cada f32 de cada rueda con la velocidad longitudinal (conducir variando la velocidad) |
| `run_agent.bat --state-diff [--hold=3000 --wait=8000] [--deep]` | Compara dos estados de memoria al pulsar un interruptor (diferencial, AWD, reductora, marcha…); `--deep` explora también los hijos de los hijos |

Código nuevo: [analysis.py](../src/snowrunner_telemetry_api/analysis.py), [physics.py](../src/snowrunner_telemetry_api/physics.py),
[coverage.py](../src/snowrunner_telemetry_api/coverage.py), [context.py](../src/snowrunner_telemetry_api/context.py),
[autorecord.py](../src/snowrunner_telemetry_api/autorecord.py), `dashboard/{app,view,advice,recorder}.py`,
`agent/Program.{FindSingletons,ThrottleFind,StateFind}.cs`. Procedimiento de calibración: [CALIBRACION.md](CALIBRACION.md).
Tests: `python -m pytest` (**88 pasan**).

## Cálculos derivados (`physics.py`)

Se calculan en vivo para el dashboard y en lote para el análisis (`analysis.enrich`):

| Magnitud | Cómo se calcula | Para qué |
| -------- | --------------- | -------- |
| Eje delantero | Columna de `rot` más alineada con la velocidad al avanzar (≥ 25 muestras > 3 km/h); se re-verifica por camión y se guarda como a priori en `data/forward_axis.json` | Base de lo demás. Columna 0, signo + (Scout 800, alineación 0,997) |
| Cabeceo, alabeo, pendiente (%) | Del eje delantero y el eje «arriba». **Alabeo + = costado derecho arriba** (corregido hoy: estaba invertido) | Pendiente real, no estimada con `vel.y` |
| Aceleración neta | medida + g·sen(cabeceo) | Lo que aporta el motor, independiente de la pendiente |
| Fuerza lateral (g) | v_long × guiñada / g | Giros bruscos |
| Distancia | Suma de desplazamientos de `pos` (ignora saltos > 50 m) | Consumo por km |
| Consumo L/h y L/100 km | Caída de `fuel_liters_raw` | Eficiencia por gas y terreno |
| **Patinaje por rueda** | (ω·R − v) / máx(v, 2 m/s), con R = mediana de v/ω de todas las ruedas en movimiento (calibrado por camión; solo con v > 1 m/s); también `slip_over_max_ms` | Dónde el gas extra solo hace girar las ruedas |

Cobertura de grabación: 60 s por cada uno de los 5 tramos de gas (5–25, –50, –75, –95, ≥95 %) por camión × terreno ×
etiquetas × pendiente. Tope opcional (`--cap-seconds`): una situación ya cubierta guarda solo 1 de cada 5 filas.

## Pendiente de descubrir en memoria

Técnica general (la que ha funcionado con gas, volante, freno y ruedas): correlacionar cada f32 del vehículo y de los
objetos a los que apunta con una señal conocida mientras el usuario actúa (`--throttle-find`, `--wheel-find`), o comparar
dos estados al pulsar un interruptor (`--state-diff`).

| Prioridad | Dato | Por qué | Cómo encontrarlo |
| --------- | ---- | ------- | ---------------- |
| 1 | **Marcha actual y reductora (L)** | Cambian la aceleración y el consumo; lo que más pesa en barro | `--state-diff` cambiando de marcha / pulsando L, con un camión que las tenga |
| 2 | **Bloqueo de diferencial y AWD** | Afecta a tracción en barro | `--state-diff --deep` con un camión con esos controles (Fleetstar, Tatra, Bandit); confirmar en el HUD que el control responde durante la captura |
| 3 | **RPM del motor** | Ver en qué zona de la curva de torque se trabaja (lo que ajusta el mod). Candidato antiguo `vehicle+0x114` probablemente muerto | Correlación con velocidad y marcha |
| 4 | **Masa total / carga / remolque** | Con masa y aceleración neta se estima la potencia a las ruedas (P = m·a·v) y se compara con el motor del XML | `rb+0xB8 → +0xA4` **no vale** (el cuerpo principal pesa ~50 kg); la lectura de la «isla de simulación» `rb+0x128` da valores basura. Probar `attach_manager +0x78` y `cargo_manager +0x1E8`, o sumar masas de los cuerpos reales |
| 5 | **Daño de motor y ruedas** | Sesga las medidas de potencia | Difícil: solo cambia al dañarse |
| 6 | Freno de mano | Separar maniobras | Junto al bloque de entradas `veh+0x68→+0x40…` |
| — | `veh+68→+B0` ([−0,49, 0,49]) | Varía con el volante: ¿ángulo real de las ruedas? | Comparar con `steer_game` |
| — | `w_speed` (`+0x2DC`) | Entender su significado | Comparar con la velocidad de cada rueda |

### Resultado de la búsqueda de interruptores (2026-10-21)

`--state-diff` en el Scout 800 solo dio 7 campos estables que cambian y todos eran ruido de punteros del objeto
`veh+0x20`: **no se halló ningún interruptor**. O el control no existe en ese camión o no se pulsó, o el estado está más
profundo (`--deep`). Hay que repetirlo con un camión que tenga los controles y comprobar en el HUD que cambian.

## Sesiones del 2026-10-21 y lo que enseñaron

Ficheros en `data/sessions/` (gitignored). Las dos últimas son las fiables (combustible directo).

| Sesión | Qué es | Utilidad |
| ------ | ------ | -------- |
| `dash_s_international_scout_800_…_215841` | 12 min de **subida continua** (+13,6 %, 38→140 m), combustible interpolado, sin etiquetas | Aceleración neta, patinaje, inclinación y uso de gas. **No** sirve para eficiencia (consumo modelado + pendiente) |
| `dash_s_tatra_t813_…_221934` | 9 min en **llano**, 8 ruedas, combustible directo, gas nunca > 75 % | La mejor hasta ahora: base del perfil del Tatra. Faltan los tramos de gas 75–95 % y ≥ 95 % |
| `dash_s_krs_58_bandit_…_221710` | 57 s casi parado | Solo valida capacidad (150 L) |
| `play_…_205819` | Sesión antigua del Scout, combustible interpolado, sin orientación | Solo histórico |

- **Volante:** el signo actual correlaciona **+0,74 (Scout) / +0,81 (Tatra) con la guiñada** y **−0,37 / −0,53 con la
  aceleración hacia la columna 2 de `rot`**: coherente entre camiones, pero el **sentido físico (izquierda/derecha) sigue
  sin confirmar**. Prueba pendiente: girar a fondo a la derecha y mantener 5 s, y leer el signo.
- **Consumo** (muy acelerado respecto a la realidad, comparar solo entre tramos): Tatra ≈ 300 L/h a 8 km/h de media,
  Scout ≈ 88–235 L/h, Bandit atascado ≈ 149 L/h.
- **Eficiencia del Tatra (llano):** en terreno duro y mixto, el gas bajo (5–25 %) sale el más eficiente (≈ 2500 L/100 km
  frente a 4000–5400 con gas medio) **y a mayor velocidad** (10 frente a 6–8 km/h). **Es correlación, no causa**: el
  conductor da más gas donde el terreno es más difícil. Hacen falta barridos de gas constante sobre el mismo tramo.
- **Patinaje del Tatra:** +18–24 % de media, 28 % de las filas por encima del 30 %. Se disparaba a baja velocidad
  (+47 % a 4–5 km/h, +2–3 % a > 9 km/h) con una diferencia absoluta casi constante (+0,2…0,7 m/s); por eso ahora hay suelo
  de 2 m/s en el denominador.
- **Fiabilidad del combustible:** `FuelSessionTracker` no lee, **modela**, y recibía el acelerador antiguo (roto). Las
  sesiones grabadas antes de añadir `fuel_liters_raw` (fuente `ce_fuel_hud+tracked`) **no sirven para consumo**; el informe
  avisa con `AVISO`. Corregido: el agente emite `fuel_liters_raw`, el tracker usa `throttle_game` y el análisis usa el directo.
- **Terreno:** el clasificador parpadea (hasta 7 cambios/min, 61 tramos de < 1 s en 12 min) y marca «ice» (grip 0,03,
  surface 0,88) donde probablemente hay suelo duro. Revisar `terrain_classifier.py` para camiones distintos del Bandit.

## Plan para la próxima sesión

1. Verificar offsets y entradas (arriba).
2. **Grabar con etiquetas y barridos de gas** (lo que más valor da): por camión y terreno, pasadas sobre el mismo tramo con
   gas constante ≈ 30 / 50 / 70 % y a fondo, ≥ 10 s (mejor 60 s) por tramo, con `set_context.py carga=… neumaticos=…`.
   Procedimiento en [CALIBRACION.md](CALIBRACION.md).
3. Confirmar el sentido del volante (girar a fondo a la derecha 5 s).
4. Buscar **marcha, reductora, diferencial y AWD** con `--state-diff` en un camión que los tenga.
5. Informe de **freno motor** (deceleración con gas = 0 por velocidad, pendiente y terreno).
6. Revisar el clasificador de terreno para el Scout y el Tatra.
7. Con perfiles reunidos: `report_profiles.py --write-ideal --write-efficiency`, comparar con
   `camiones/<id>/FASES.md` y el simulador (`python -m camiones.<id>.simulador`), ajustar `patches.py`, `apply_mod.py` y
   repetir la grabación (las sesiones se separan por el SHA1 del pak guardado en `_meta`).

## Preguntas abiertas

- **Pak del mod no aplicado.** El de Steam es vanilla (SHA1 `cf8e1cbf…`). Para comparar mod vs vanilla hay que ejecutar
  `apply_mod.py` (en `snowrunner real`) y repetir. El mod baja el depósito del Bandit a 135 L: es una comprobación gratuita
  de que la capacidad se lee de memoria.
- La aceleración depende de pendiente, marcha, carga y daño; el «gas ideal» significa «a partir de aquí más gas no sube la
  aceleración neta», no un óptimo físico.
- Resolución real de la lectura directa del combustible parado: no cambia (72 L fijos en 15 s); en marcha cambia cada
  muestra.
- Faltan banderas de calidad por fila (juego en pausa, saltos de `sample_seq`).

## Detalles prácticos

- **Nada está commiteado.** Hay muchos cambios sin commit, incluidos anteriores a esta sesión (`WheelTerrainReader.cs`,
  `terrain_classifier.py`, …). Sugerencia de commits temáticos: (1) agente C# — offsets, singletons, entradas del conductor,
  orientación, ruedas, combustible directo; (2) paquete Python — análisis, física, cobertura, contexto, grabación;
  (3) dashboard; (4) scripts y herramientas; (5) documentación y tests.
- `data/sessions/`, `data/accel_*.json`, `data/game_catalog.json`, `data/context.json`, `data/coverage.json`,
  `data/ideal_throttle.json`, `data/efficiency.json` y `data/forward_axis.json` están en `.gitignore`.
- Cerrar el dashboard con la X; si se mata a la fuerza queda un proceso `dotnet` huérfano del agente (hay que cerrarlo).
- El dashboard fuerza `--memory-only` para el agente; las entradas del conductor se leen de memoria, no del pedal.
- Las rutas del juego se pueden cambiar con `SNOWRUNNER_GAME_DIR`.
- Consolas Windows cp1252: los scripts de informe fuerzan UTF-8 (`console.py`); si se lanza Python suelto con símbolos
  (→, ●), usar `PYTHONIOENCODING=utf-8`.
