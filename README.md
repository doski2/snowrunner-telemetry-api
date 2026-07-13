# SnowRunner Telemetry API

Proyecto **separado** del mod realista (`snowrunner real`). Su rol es **obtener y exponer datos** del juego; el proyecto principal **calcula, compara y gestiona** (sim, parches, calibración, índices).

```
┌─────────────────────────────┐         ┌──────────────────────────────┐
│  snowrunner-telemetry-api   │  HTTP   │      snowrunner real         │
│  (este repo)                │ ──────► │  (mod + sim + telemetría)    │
│                             │  JSON   │                              │
│  · leer memoria / agente    │         │  · importar / comparar MAE   │
│  · normalizar muestras      │         │  · camiones/, sim/, datos/   │
│  · sesiones en tránsito     │         │  · apply_mod, calibración    │
└─────────────────────────────┘         └──────────────────────────────┘
         ▲
         │ SnowRunner.exe (Windows, en ejecución)
```

## Por qué existe este proyecto

Hoy **todo está acoplado** en un solo árbol Python:

| Hoy | Problema |
|-----|----------|
| `grabar_ce.py` + `memoria_havok.py` leen RAM en el mismo proceso | Solo Windows, juego abierto, permisos CE |
| CSV en `Documents\My Games\SnowRunner\base\` | Ruta fija, un consumidor, difícil automatizar |
| `importar_ce_csv.py` asume archivo local | No hay frontera clara adquisición ↔ análisis |

Una **API de telemetría** desacopla:

1. **Adquisición** — quién lee Havok, cuándo, desde qué máquina.
2. **Contrato** — muestras y sesiones en JSON estable (mismo esquema que `telemetria.py`).
3. **Consumo** — el proyecto principal importa por HTTP/archivo sin tocar memoria.

## Estado actual

**Fase 0 — Investigación** (documentación; sin endpoints en producción).

**Decisión clave:** agente de memoria en **C# nativo** (Win32), API HTTP en **Python FastAPI**. Ver [INVESTIGACION.md](docs/INVESTIGACION.md) §3 G.

| Documento | Contenido |
|-----------|-----------|
| [docs/CONTEXTO.md](docs/CONTEXTO.md) | Necesidad, alcance, qué no hace la API |
| [docs/INVESTIGACION.md](docs/INVESTIGACION.md) | Alternativas, pasos previos, riesgos |
| [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md) | Diseño propuesto (agente + API) |
| [docs/CONTRATO-DATOS.md](docs/CONTRATO-DATOS.md) | Campos y formatos alineados con `snowrunner real` |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Orden de trabajo antes del primer `curl` |

## Relación con el proyecto principal

| Repositorio | Ruta local (referencia) | Responsabilidad |
|-------------|-------------------------|-----------------|
| **Este** | `snowrunner-telemetry-api/` | Obtener datos, API, agente opcional |
| **Principal** | `snowrunner real/` | Simulación, mod `.pak`, MAE, `datos/`, `camiones/` |

El principal **no debe** duplicar lectura de memoria a largo plazo; debe consumir la API o JSON exportado por este proyecto.

## Próximo paso

Leer [docs/INVESTIGACION.md](docs/INVESTIGACION.md) y cerrar decisiones marcadas como **DECISIÓN PENDIENTE** antes de implementar endpoints.
