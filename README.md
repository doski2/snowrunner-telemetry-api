# SnowRunner Telemetry API

API HTTP de telemetría Havok, separada del mod realista (`snowrunner real`).

**Fase 1:** lee la última fila de `telemetria_ce_log.csv` y expone JSON `ce_sample_v1`.

## Requisitos

- Python 3.11+
- Windows (CSV en `Documents\My Games\SnowRunner\base\`)
- `grabar_ce.py` grabando o CSV existente

## Instalación

```powershell
cd snowrunner-telemetry-api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -e ".[dev]"
# Dashboard GUI (matplotlib)
pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -e ".[dashboard]"
```

El repo incluye `.venv` local (gitignored). Cursor debe usar **`.venv\Scripts\python.exe`** como intérprete.

## Arrancar API

```powershell
# Recomendado
python -m snowrunner_telemetry_api

# O doble clic / terminal
.\run_api.bat
```

No ejecutes `main.py` a solas (fallan los imports relativos). Si el IDE lanza `main.py`, usa la config **API — snowrunner_telemetry_api** en `.vscode/launch.json`.

```powershell
# Alternativa uvicorn
uvicorn snowrunner_telemetry_api.main:app --host 127.0.0.1 --port 8765
```

Variables opcionales:

| Variable | Default |
|----------|---------|
| `SNOWRUNNER_API_PORT` | `8765` |
| `SNOWRUNNER_CSV_PATH` | `%USERPROFILE%\Documents\My Games\SnowRunner\base\telemetria_ce_log.csv` |

## Probar con curl

```powershell
curl http://127.0.0.1:8765/v1/health
curl http://127.0.0.1:8765/v1/status
curl http://127.0.0.1:8765/v1/sample
```

**Éxito:** `/v1/sample` devuelve `schema_version`, `vehicle_id`, `speed_kmh` coherentes con la última línea del CSV.

## Dashboard (velocidad y combustible)

GUI Python con valores en vivo y histórico opcional (`speed_kmh`, `fuel_pct`).

```powershell
# Modo auto (default): agente C# si SnowRunner está abierto; si no, API CSV (solo si grabar_ce activo)
.\run_dashboard.bat

# Solo agente C# (juego abierto en mapa, sin grabar_ce.py)
.\run_dashboard.bat --source agent

# Solo API CSV (requiere .\run_api.bat + grabar_ce.py)
.\run_api.bat
.\run_dashboard.bat --source api
```

Opciones: `--interval=250 --history=600 --chart=fuel_pct --url=http://127.0.0.1:8765`

En la ventana, desplegable **Gráfico:** Velocidad / Combustible / Ambos (solo con Histórico activo).

Requiere `pip install -e ".[dashboard]"` (matplotlib).

## Tests

```powershell
pytest
```

O todo el checklist Fase 1 en un solo paso:

```powershell
.\fase1_comprobar.bat
```

Comprueba: `pip install`, pytest, CSV en Documents, endpoints `/v1/*` y (si el puerto 8765 está libre) una petición HTTP en vivo.

## Documentación

| Documento | Contenido |
|-----------|-----------|
| [docs/ROADMAP.md](docs/ROADMAP.md) | Fases del proyecto |
| [docs/CONTRATO-DATOS.md](docs/CONTRATO-DATOS.md) | Esquema `ce_sample_v1` |
| [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md) | Agente C# + API (Fase 2+) |
| [docs/RESUMEN.md](docs/RESUMEN.md) | **Síntesis** de todo lo hecho hasta ahora |

**Repo:** https://github.com/doski2/snowrunner-telemetry-api

## Throttle legacy (CSV antiguo)

Si falta `throttle_input` en el CSV:

- Se usa `throttle` como input **solo si** no es `-1` (valor no fiable en grabaciones viejas).
- `throttle` en la respuesta = `throttle_input` → `throttle_motor` → `throttle` crudo.

Ver `src/snowrunner_telemetry_api/sample.py`.

## Estado

| Fase | Estado |
|------|--------|
| 0 — Investigación | ✅ |
| 1 — API CSV | ✅ |
| 2 — Agente C# | **2.0** scaffold + **2.1** spike ✅ — ver `agent/` |

Tras un **patch de Steam** que rompa offsets: checklist en [docs/ROADMAP.md](docs/ROADMAP.md#mantenimiento-tras-patch-del-juego-continuo-no-bloquea-fase-3) (tareas 2.7–2.8).

## Agente C# (Fase 2.0 / 2.1)

```powershell
.\fase2_comprobar.bat    # checklist build + offsets (+ probe si hay juego)
.\run_agent.bat          # una muestra JSON
.\run_agent.bat --loop   # poll continuo
```

Detalle de entregables: [docs/ROADMAP.md](docs/ROADMAP.md#fase-20--scaffold-) y [agent/README.md](agent/README.md).
