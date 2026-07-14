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
pip install -e ".[dev]"
```

## Arrancar API

```powershell
# Opción A — módulo
python -m snowrunner_telemetry_api

# Opción B — uvicorn directo
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

## Tests

```powershell
pytest
```

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
| 2 — Agente C# | pendiente |
