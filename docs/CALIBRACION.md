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

## Eficiencia por situación: cuánto acelerar para gastar menos

Objetivo: saber, para cada camión, terreno y configuración, **qué tramo de gas da menos L/100 km**
(no menos L/h: con poco gas avanzas poco y gastas mucho por metro).

### 1. Etiquetar la situación (se aplica en caliente, sin reiniciar nada)

```powershell
python scripts/set_context.py carga=vacio "neumaticos=Ultima AT I" diff=on
python scripts/set_context.py --show        # ver las etiquetas activas
python scripts/set_context.py --unset diff  # quitar una
python scripts/set_context.py --clear       # quitar todas
```

Cada fila grabada lleva las etiquetas vigentes (`ctx`); el informe agrupa por camión, terreno y etiquetas,
así que **cámbialas siempre que cambies carga, neumáticos, diferencial o reductora**. Claves
sugeridas: `carga` (vacio / bastidor / remolque), `neumaticos`, `diff`, `reductora`, `awd`. Mientras
no leamos peso, neumáticos ni marcha de memoria, las etiquetas son la única forma de separarlos.

### 2. Grabar

- **Juego normal:** `record_play.bat` (perfil general).
- **Barrido de gas** (imprescindible): en juego normal casi solo se pisa a fondo o se suelta, así que
  los gases intermedios apenas aparecen y no se puede hallar el óptimo. Para cada combinación
  (terreno × etiquetas), recorre el mismo tramo varias veces con gas constante ≈ 30 %, 50 %, 70 %
  y 100 %, al menos **10 s en cada tramo** (mejor 60 s para confianza «alta»).

### 3. Analizar

```powershell
python scripts/report_profiles.py --efficiency            # tabla en pantalla
python scripts/report_profiles.py --write-efficiency      # data/efficiency.json (el dashboard la usa)
python scripts/report_profiles.py --write-ideal           # gas con más aceleración neta
```

Para cada situación el informe da, por tramo de gas (0,05–0,25 / –0,50 / –0,75 / –0,95 / ≥0,95):
segundos, metros, litros, **L/100 km**, velocidad media y aceleración neta; marca el tramo más
eficiente, cuánto más gasta el gas a fondo y la **confianza** (alta / media / baja). La línea
«faltan por grabar» lista los tramos con < 10 s: es lo que te falta por cubrir.

El dashboard muestra, bajo el gas, «eficiente 50–75 % (~38 L/100 km) · a fondo +35 %» para el terreno
y las etiquetas actuales, y las etiquetas activas en la tarjeta del camión.

### Cómo leer el resultado

- Los L/100 km son **relativos**: el consumo del juego va muy acelerado (un Scout al 68 % de gas gasta
  ~88 L/h), así que importa la comparación entre tramos, no el valor absoluto.
- El tramo elegido necesita ≥ 10 s y ≥ 30 m de avance. Un tramo con casi cero avance (patinando o
  hundido) aparece con L/100 km enormes y nunca se elige.
- Tracción: hasta descubrir el giro de ruedas, el avance real por litro y la aceleración neta son
  el indicador de tracción; `wheel_grip`/`contact`/`surface_deform` se graban en cada fila.

## Grabación automática, tamaño y cobertura

- **El dashboard graba siempre al abrirse** (`--no-record` lo desactiva). Un fichero por camión en
  `data/sessions/dash_<vehicle_id>_<fecha>.ndjson`, con cabecera `_meta`, etiquetas de contexto por fila y
  aligerado del ralentí. `record_play.bat` hace lo mismo sin ventana (prefijo `play_`).
- **Fila mínima:** solo los 27 campos que usan los análisis (≈ 650 B por fila frente a 1335 B de la fila completa;
  ≈ −50 %). `--full-rows` guarda todo el JSON del agente.
- **Volumen:** a 10 Hz son ≈ 20–25 MB por hora de conducción con fila mínima. Para ahorrar espacio:
  `python scripts/compact_sessions.py` comprime las sesiones terminadas a `.ndjson.gz` (≈ 10× menos; verifica antes de
  borrar y omite las modificadas hace < 15 min). Los informes leen `.ndjson` y `.ndjson.gz`.
- **Cobertura** (`data/coverage.json`): segundos acumulados por camión × terreno × etiquetas × pendiente × tramo de gas.
  La tarjeta *Grabación* muestra, para la situación actual, el % completo (meta: 60 s en cada uno de los 5 tramos) y
  qué tramos de gas faltan, p. ej. «mud · carga=vacio: 40 % completo · falta gas 50–75 %, ≥95 %».
  `python scripts/report_profiles.py --rebuild-coverage` la recalcula desde las sesiones (hazlo si borras o importas sesiones).
- **Tope opcional** (`--cap-seconds=120`, desactivado por defecto): cuando una situación ya acumula ese tiempo, solo se guarda
  1 de cada 5 filas. La situación incluye camión, terreno, etiquetas y **pendiente** (llano / subida / bajada); si no etiquetas el
  peso, cargado y vacío cuentan como la misma situación. Recomendación: activarlo cuando ya haya horas de datos; mientras tanto,
  grabar todo permite reanalizar con métricas futuras (giro de ruedas, masa).

## Limitaciones conocidas

- `fuel_cap_liters` se lee de memoria junto al campo de litros; si la fuente acaba en `+cap_default`

  es la constante 210 y `fuel_pct` no es fiable. Validado solo con el Fleetstar (240 L).

- La resolución de `fuel_liters` puede ser demasiado gruesa para consumos en ralentí en sesiones

  cortas; grabar varios minutos.

- El análisis de barro depende del clasificador de terreno (`terrain_kind`).

Traspaso entre sesiones: [PENDIENTE-SESION.md](PENDIENTE-SESION.md).
