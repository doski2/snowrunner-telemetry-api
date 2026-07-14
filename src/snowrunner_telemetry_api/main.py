"""FastAPI — Fase 1 (modo CSV).

No ejecutar este archivo directamente salvo desde el IDE.
Preferido: python -m snowrunner_telemetry_api
"""

from __future__ import annotations

# Permite: python src/snowrunner_telemetry_api/main.py (IDE / Run)
if __name__ == "__main__" and __package__ is None:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "snowrunner_telemetry_api"

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from .config import API_VERSION
from .logic import SampleReadError, health_payload, read_sample_payload, status_payload

app = FastAPI(
    title="SnowRunner Telemetry API",
    version=API_VERSION,
    description="Telemetría Havok — Fase 1: lectura CSV",
)


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "name": "SnowRunner Telemetry API",
        "version": API_VERSION,
        "agent_mode": "csv",
        "docs": "/docs",
        "endpoints": {
            "health": "/v1/health",
            "status": "/v1/status",
            "sample": "/v1/sample",
        },
    }


@app.get("/v1/health")
def health() -> dict[str, Any]:
    return health_payload()


@app.get("/v1/status")
def status() -> dict[str, Any]:
    return status_payload()


@app.get("/v1/sample")
def sample() -> JSONResponse:
    try:
        payload = read_sample_payload()
    except SampleReadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return JSONResponse(content=payload)


if __name__ == "__main__":
    from snowrunner_telemetry_api.__main__ import main

    main()
