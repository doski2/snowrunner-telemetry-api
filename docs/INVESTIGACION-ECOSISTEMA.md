# Investigación — ecosistema externo (GitHub, foros, docs)

Recopilación **antes de Fase 1**. Objetivo: saber qué existe fuera de `snowrunner real`, qué se puede reutilizar y qué no hay que reinventar.

**Conclusión adelantada:** no existe un proyecto que exponga telemetría SnowRunner lista para consumir (HTTP, UDP, shared memory). Lo más cercano a vuestro trabajo es **ingeniería inversa Havok** en Cheat Engine; el repo comunitario más alineado es [FindMuck/SnowRunner_Noclip](https://github.com/FindMuck/SnowRunner_Noclip).

---

## 1. Mapa por tipo de dato

| Tipo | ¿Existe algo usable? | Ejemplos |
|------|----------------------|----------|
| **Telemetría en vivo** (velocidad, pedal, terreno) | **No oficial**; solo memoria / CE | `memoria_havok.py` (vuestro), FindMuck Noclip |
| **API HTTP / UDP / SimHub** | **No** | SCS SDK solo ETS2/ATS |
| **Datos estáticos** (camiones, masas XML, addons) | **Sí** | Saber modding docs, SnowRunnerTool |
| **Save games** | **Sí** (no telemetría) | Save Editor, SnowRunner-Tool |
| **Offsets / estructuras Havok** | **Parcial** (versionado, comunidad pequeña) | SnowRunner_Noclip `mappings.md`, FearLess CE |
| **Re-encontrar singletons tras patch** | **Sí (herramientas)** | CE_RTTI_Reverse_Lookup |

---

## 2. SnowRunner — memoria y reverse engineering

### 2.1 FindMuck/SnowRunner_Noclip ⭐ más relevante

- **Repo:** https://github.com/FindMuck/SnowRunner_Noclip  
- **Qué hace:** script CE Lua para noclip de vehículos vía Havok.  
- **Por qué importa:** usa los **mismos anclas** que vuestro `memoria_havok.py`:
  - singleton `TRUCK_CONTROL`
  - `TRUCK_CONTROL + 0x8` → vehículo activo
  - `hkpRigidBody`, `hkpSimulationIsland`, addons
- **Documentación:** [`mappings.md`](https://github.com/FindMuck/SnowRunner_Noclip/blob/main/mappings.md) — notas de estructuras y offsets (build Season 8 / patch antiguo).
- **Combustible (lead):** en `mappings.md` documentan `addon + 0x568` (litros) y `+0x56C`/`+0x570` (capacidad) en build Season 8 — ver [§11 Combustible](#11-combustible--leads-externos-y-validación).
- **Utilidad para nosotros:**
  - Validar cadenas de punteros al portar el agente C#
  - Comparar offsets cuando un update rompa lectura (ej. ellos `veh+0x5C8` → rigid body; nosotros `OFF_RB = 0x5D0` en build jun-2026 — **no copiar ciegamente**)
  - Metodología: structure dissect, pointerscan, island completo

### 2.2 FindMuck/CE_RTTI_Reverse_Lookup ⭐ mantenimiento offsets

- **Repo:** https://github.com/FindMuck/CE_RTTI_Reverse_Lookup  
- **Qué hace:** en CE, busca clases C++ por nombre RTTI (ej. `TRUCK_CONTROL`) y devuelve candidatos de instancia/singleton.  
- **Utilidad:** re-localizar `TRUCK_CONTROL_OFF` tras update Steam sin escanear a ciegas.  
- **Relacionado:** [r3sus/CE_RTTI_Scanner](https://github.com/r3sus/CE_RTTI_Scanner), issue CE [#1159](https://github.com/cheat-engine/cheat-engine/issues/1159).

### 2.3 FearLess Cheat Engine — tablas comunitarias

- **Foro:** https://fearlessrevolution.com (hilos "Snowrunner table request")  
- **Qué hay:** tablas CE (daño, dinero, reparación, etc.) mantenidas por usuarios (LML17, BLISQ, …).  
- **Limitaciones:**
  - Se rompen con updates frecuentes
  - Enfoque cheats, no telemetría estructurada
  - Comentarios sobre crashes al escanear en builds recientes (posible protección anti-debug)
- **Utilidad:** referencia de AOB/offsets puntuales; no sustituye vuestro pipeline.

### 2.4 Frida (tickelton) — enfoque alternativo

- **Artículo:** https://tickelton.gitlab.io/articles/cheating-with-frida/  
- **Script:** https://github.com/tickelton/misc.re/blob/master/frida-snowrunner-trainer.py  
- **Qué hace:** attach a `snowrunner.exe`, `Process.enumerateRanges`, `Memory.scanSync` para dinero/rango/XP.  
- **Utilidad:** patrón de descubrimiento programático; **no** cubre vehículo/terreno. Podría servir para spikes de búsqueda, no para producción de telemetría.

### 2.5 TelemetryLogger.lua (propio — legacy)

- En `snowrunner real/cheat_engine/TelemetryLogger.lua`  
- Mismo CSV que `grabar_ce.py`; intervalo 500 ms en CE.  
- **Estado:** legacy; el camino activo es Python → futuro agente C#.

---

## 3. SnowRunner — datos estáticos y archivos (no en vivo)

### 3.1 Hendrik2319/SnowRunnerTool

- **Repo:** https://github.com/Hendrik2319/SnowRunnerTool  
- Lee `initial.pak`: trucks, trailers, addons; parsea saves.  
- **Útil para:** catálogo, masas XML, nombres internos — complementa `datos/catalog_lookup.py`.  
- **No sirve para:** muestras en tiempo real.

### 3.2 chase-000/SnowRunnerTools

- **Repo:** https://github.com/chase-000/SnowRunnerTools  
- Pack/unpack PAK, `cache_block`, utilidades de modding.  
- **Útil para:** pipeline `.pak` del mod realista, no telemetría.

### 3.3 Editores de save

| Proyecto | Enlace | Notas |
|----------|--------|-------|
| MrBoxik/SnowRunner-Save-Editor | https://github.com/MrBoxik/SnowRunner-Save-Editor | GUI Python, seasons 1–17 |
| elpatron68/SnowRunner-Tool | https://github.com/elpatron68/SnowRunner-Tool | Backups F2 in-game, .NET |

Fuera de alcance de la API de telemetría.

---

## 4. Documentación oficial Saber (modding)

- **Base:** https://expeditions-guides.saber.games/  
- **Contenido:** XML de camiones, `PhysicsModel`, masas, ruedas, constraints Havok en **datos de diseño**.  
- **Útil para:**
  - Entender nombres de bones, collision meshes `_cdt`
  - Masas vacías de referencia (`empty_mass` en XML vs Havok runtime)
  - Validar `vehicle_id` y specs del mod
- **No proporciona:** lectura de memoria, telemetría, offsets runtime.

---

## 5. Familia MudRunner / Spintires (motor anterior)

| Tema | Fuente | Relevancia |
|------|--------|------------|
| VeeEngine + Havok | [Spintires Wiki](https://spintires.fandom.com/wiki/VeeEngine) | MudRunner usa VeeEngine; SnowRunner usa **Swarm Engine** (distinto) |
| Simulación barro | [mudrunnermods.com](https://www.mudrunnermods.com/the-mud-of-mudrunner/) | Contexto físico; offsets **no** transferibles |
| Havok Visual Debugger | Guía modding Spintires Editor | Solo editor/dev, no juego retail en marcha |

**Conclusión:** inspiración conceptual (Havok, ruedas, carga), no código reutilizable directo.

---

## 6. Referencia: cómo lo hacen los simuladores con API real (SCS)

SnowRunner **no** tiene equivalente. Sirve como **modelo objetivo** de arquitectura:

| Recurso | Enlace | Qué demuestra |
|---------|--------|---------------|
| SCS Telemetry SDK | foro scssoft.com | Plugin DLL + shared memory `Local\SCSTelemetry` |
| truckermudgeon/scs-sdk-plugin | GitHub | Contrato `scsTelemetryMap_t` estable |
| hehecau/scs-sdk-python | GitHub | Cliente Python lee shared memory |
| scs-telemetry-shared-memory (Rust) | lib.rs | Layout `#[repr(C)]` documentado |

**Lección para nuestro proyecto:** el juego debería exponer un contrato fijo; como no lo hace, nosotros somos el “plugin + API” vía memoria + FastAPI.

---

## 7. Librerías genéricas de lectura de memoria

| Librería | Enlace | Notas |
|----------|--------|-------|
| PyMemoryEditor | https://github.com/JeanExtreme002/PyMemoryEditor | `read_process_memory`, `search_by_addresses` (lee página entera) — patrón útil para agente C# batched |
| ctypes + kernel32 | `memoria_havok.py` | Lo que ya usáis |
| Frida | tickelton | Discovery, no prod |

Ninguna conoce SnowRunner; solo abstraen Win32.

---

## 8. Foros y comunidad (telemetría)

| Fuente | Resultado |
|--------|-----------|
| [SimHub — SnowRunner](https://www.simhubdash.com/community-2/simhub/snowrunner/) | **Sin soporte** — juego no expone telemetría |
| [GitHub SimHub #785](https://github.com/SHWotever/SimHub/issues/785) | Cerrado: limitación técnica |
| [Steam — Telemetry For Sims](https://steamcommunity.com/app/1465360/discussions/) | Sin solución estable |
| [Focus community — idea telemetría](https://community.focus-entmt.com/focus-entertainment/snowrunner/ideas/10339) | Petición sin implementación oficial |

---

## 9. Qué reutilizar vs qué construir nosotros

### Reutilizar / consultar

- [ ] Metodología y `mappings.md` de SnowRunner_Noclip al portar agente C#
- [ ] CE_RTTI_Reverse_Lookup cuando cambie `TRUCK_CONTROL_OFF`
- [ ] Docs Saber para masas XML y nombres de clase
- [ ] SnowRunnerTool / catálogo para enriquecer `meta.setup`
- [ ] Patrón SCS shared memory como **referencia de diseño** (nuestro contrato JSON = su `TelemetryMap`)
- [ ] PyMemoryEditor: idea de lectura por páginas en el agente nativo

### No existe — hay que construirlo (este repo)

- [ ] API HTTP localhost (`/v1/sample`, sesiones)
- [ ] Agente C# con lecturas batched Havok
- [ ] `throttle_resolver` por vehículo
- [ ] Contrato `ce_sample_v1` / `ce_session_v1`
- [ ] Integración con `comparar_telemetria` del principal

### No perseguir

- Integración SimHub / UDP tipo ETS2 (sin datos del juego)
- Fork de tablas CE como “API” (frágil, sin terreno/carga)
- Offsets de MudRunner/Spintires en SnowRunner actual

---

## 10. Posición de `snowrunner real` vs comunidad

| Capacidad | Comunidad típica | Vuestro principal |
|-----------|------------------|-------------------|
| Singleton TRUCK_CONTROL | Noclip, cheats | ✅ `memoria_havok.py` |
| Velocidad / posición Havok | Noclip | ✅ |
| Terreno por rueda (grip, contact) | Raro / no publicado | ✅ `read_wheel_terrain` |
| Carga / payload / trailer | No visto en repos públicos | ✅ `read_vehicle_load` |
| Throttle input vs motor | No visto | ✅ `throttle_resolver` |
| CSV ~50 columnas + import MAE | **Único** en ecosistema abierto | ✅ |

**Implicación:** no hay repo GitHub para clonar como agente. El port C# sale de **vuestro** `memoria_havok.py`, usando FindMuck solo como **validación cruzada**.

---

## 11. Combustible — leads externos y validación

Ningún repo público documenta el patrón **dos familias de campos** (consumo vs repostaje) que estamos viendo en build jun-2026. Lo más cercano es FindMuck; el resto son tablas CE sin estructura.

### 11.1 Lead FindMuck (`mappings.md`, Season 8)

En el addon manager (`veh + 0x58` en Season 8; nosotros `veh + 0x48`):

| Offset (Season 8) | Campo documentado |
|-------------------|-------------------|
| `addon + 0x868` | **f32 % HUD** (~0.945 → 199 L en scan jul-2026) |
| `vehicle + 0x728` | **f32 litros** (~200 L; confirma con +868) |
| `addon + 0x568` | Combustible actual (Season 8 FindMuck; no visto en scan 199 L) |
| `addon + 0x56C` | Capacidad máxima |
| `addon + 0x570` | Capacidad (ruta UI) |

**No copiar offsets** — validar en build actual con `--fuel-scan`. Si `addon+568` sigue vivo, simplificaría mucho `FuelReader` frente a probes `+130→+05C` / `+128→+040`.

### 11.2 Patrón observado (build jun-2026, Fleetstar 210 L)

| Familia | Cuándo vive | Ejemplos | Congela cuando… |
|---------|-------------|----------|-----------------|
| **Consumo** | Bajando combustible en marcha | `+130→+05C` f32%, `+128→+0EC` | Repostas |
| **Repostaje** | Subiendo tras llenar | `+128→+040`, `+130→+06C` | Consumes |
| **Legacy / mixto** | Inestable | `addon+008` f32 L, `addon+052` u16 | Uno u otro según fase |

El agente C# usa `FuelModeTracker` para alternar consume vs repostaje según qué campo **cambió** en el último poll. Hasta encontrar un offset único (tipo `+0x568` validado), no hay atajo en GitHub.

### 11.3 Checklist de validación (`--fuel-scan` / `--fuel-diff`)

Con SnowRunner abierto, camión en mapa, HUD visible (litros exactos):

**Paso A — baseline a N litros (ej. 171 L)**

```powershell
.\run_agent.bat --fuel-scan --target-liters=171
.\run_agent.bat --fuel-debug
```

Anotar candidatos que coincidan (±12 L o ±3 %): `addon+…`, `addon+128→child+…`, `addon+130→child+…`, `vehicle+…`.

**Paso B — tras repostar a M litros (ej. 208 L)**

```powershell
.\run_agent.bat --fuel-scan --target-liters=208
.\run_agent.bat --fuel-debug
```

Comparar con Paso A:

- Campo que **subió** con repostaje y **no bajó** al consumir antes → candidato **repostaje**.
- Campo que **bajaba** al conducir y **se congeló** al repostar → candidato **consumo**.
- Campo que coincide en **ambos** pasos con el HUD → candidato **único** (objetivo).

**Paso C — snapshot jul-2026 ~199 L** *(archivado — superseded por `ce_fuel_hud` §11.5)*

```
addon+868 f32=0.9452 pct?   → ~198.5 L  (estático al consumir)
vehicle+728 f32=200.00 L?   → confirma (±4 L)
```

Útil solo como pista en `--fuel-debug` si la cadena CE rompe; no usar como criterio de cierre.

**Paso D — lead FindMuck `+0x568`** *(no seguir salvo rotura de `ce_fuel_hud`)*

En la salida de `--fuel-scan`, buscar explícitamente:

```
addon+568 f32=… L?
```

Si aparece y sigue al HUD en A y B, añadir a `offsets_referencia.json`. Con `ce_fuel_hud` validado, este paso queda en standby.

**Paso E — diff en vivo (opcional)**

```powershell
.\run_agent.bat --fuel-diff --wait=5000
```

Conducir o repostar durante la espera; los offsets que cambian en `[fuel-diff]` son los vivos.

**Paso F — cerrar en offsets**

1. Actualizar `agent/data/offsets_referencia.json` (y copia en `snowrunner real/cheat_engine/`).
2. Probar `.\run_agent.bat --memory-only` y dashboard `--source agent`.
3. Criterio: `fuel_liters` ±2 L del HUD en consumo **y** tras repostaje; `fuel_source` estable.

### 11.5 CE pointerscan combustible (usuario jul-2026)

**Cadena validada** (varios camiones, coincide HUD):

```
SnowRunner.exe + 0x2A8EDE0
  → +0x8 → +0x68 → +0x30 → +0x2B0 → +0xA8 → +0xD0 → f32 +0x5E8
```

En `offsets_referencia.json` → `fuel_pointerscan.ce_fuel_hud` (prioridad 1). El agente la prueba **antes** que probes addon/veh (`fuel_source` = `ce_fuel_hud` si la cadena resuelve y el f32 encaja como L o %).

| Punto | Detalle |
|-------|---------|
| Campo final | `f32` en `+0x5E8` (cerca de `main_rigid_body` +0x5D0 — misma zona Havok) |
| Base estática `+0x2A8EDE0` | A **+8** de `TRUCK_CONTROL` (`0x2A8EDD8`) — misma región singleton build jun-2026 |
| Validación | Multi-vehículo jul-2026; valor = HUD en litros |
| Comprobar | `.\run_agent.bat --fuel-debug` línea `ce_fuel_hud`; conducir + repostar vs HUD |

**Cadena anterior (no validada vs HUD):**

```
SnowRunner.exe + 0x2A5D990
  → +0x20 → +0x140 → +0x7A0 → +0x8 → +0xE8 → +0xD0 → f32 +0x5E8
```

`fuel_pointerscan.ce_jul2026` — base distinta a `TRUCK_CONTROL`; se mantiene como fallback.

Si la cadena rompe tras update Steam: nuevo pointerscan o sustituir `module_offset` manteniendo offsets relativos si la estructura no cambió.

### 11.4 Qué no usar para combustible

| Fuente | Motivo |
|--------|--------|
| Tablas CE FearLess / vgtimes | Offsets por versión; escriben memoria; sin documentar consume/repostaje |
| Save Editor (MrBoxik) | Edita partida, no runtime |
| XML gearbox `FuelConsumption` | Diseño estático, no HUD en vivo |
| Offsets MudRunner / Spintires | Motor distinto |

---

## 12. Riesgos detectados en la comunidad

| Riesgo | Fuente | Mitigación nuestra |
|--------|--------|-------------------|
| Offsets por build | Noclip, FearLess | `offsets_referencia.json` + RTTI tool + `probe_ok` en `/status` |
| `TRUCK_CONTROL` cambia de dirección | mappings.md | RTTI reverse lookup |
| CE scan crashea juego | FearLess foro | Lectura pasiva `PROCESS_VM_READ` (como ahora) |
| Versiones desfasadas en GitHub | Noclip = Season 8 | No copiar offsets; copiar método |
| Sin telemetría oficial | SimHub, Focus | API propia; no esperar SDK |

---

## 13. Acciones recomendadas (pre-Fase 1)

| # | Acción | Esfuerzo |
|---|--------|----------|
| 1 | Leer `mappings.md` y comparar con `memoria_havok.py` (tabla diff offsets) | 1–2 h |
| 2 | Probar CE_RTTI_Reverse_Lookup en SnowRunner: confirmar `TRUCK_CONTROL` | 30 min |
| 3 | Anotar en `offsets_referencia.json` enlace a repos de referencia | 15 min |
| 4 | **No** bloquear Fase 1 por el port C# — CSV + API primero | — |
| 5 | Checklist combustible [§11.3](#113-checklist-de-validación---fuel-scan---fuel-diff) con HUD 171 L y tras repostaje | 30–60 min |

---

## 14. Enlaces rápidos

### SnowRunner RE / memoria
- https://github.com/FindMuck/SnowRunner_Noclip  
- https://github.com/FindMuck/CE_RTTI_Reverse_Lookup  
- https://fearlessrevolution.com (buscar "Snowrunner table")

### Datos estáticos / modding
- https://github.com/Hendrik2319/SnowRunnerTool  
- https://github.com/chase-000/SnowRunnerTools  
- https://expeditions-guides.saber.games/

### Referencia telemetría (otros juegos)
- https://github.com/truckermudgeon/scs-sdk-plugin  
- https://github.com/hehecau/scs-sdk-python  

### Genérico memoria
- https://github.com/JeanExtreme002/PyMemoryEditor  
- https://tickelton.gitlab.io/articles/cheating-with-frida/

---

Ver también: [INVESTIGACION.md](INVESTIGACION.md), [ROADMAP.md](ROADMAP.md).
