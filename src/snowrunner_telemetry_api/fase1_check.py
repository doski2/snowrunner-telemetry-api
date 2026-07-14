"""Comprobaciones Fase 1 — CSV + endpoints (sin juego obligatorio)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

from snowrunner_telemetry_api.config import csv_path
from snowrunner_telemetry_api.csv_source import read_last_row
from snowrunner_telemetry_api.logic import (
    SampleReadError,
    health_payload,
    read_sample_payload,
    status_payload,
)
from snowrunner_telemetry_api.sample import required_fields_present


def _ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def _warn(msg: str) -> None:
    print(f"  [AVISO] {msg}")


def _fail(msg: str) -> int:
    print(f"  [FALLO] {msg}")
    return 1


def check_csv() -> int:
    print("\n--- CSV Havok ---")
    path = csv_path()
    print(f"  Ruta: {path}")
    state = read_last_row(path)
    if not state.exists:
        return _fail(
            "No existe telemetria_ce_log.csv — graba con grabar_ce.py o define SNOWRUNNER_CSV_PATH"
        )
    _ok(f"Archivo encontrado ({state.row_count} filas)")
    if state.last_mtime:
        age_h = (datetime.now(tz=timezone.utc) - state.last_mtime).total_seconds() / 3600
        print(f"  Ultima modificacion: {state.last_mtime.isoformat()} ({age_h:.1f} h)")
        if age_h > 24:
            _warn("CSV con mas de 24 h — puede no reflejar la sesion actual")
    if state.error:
        return _fail(f"Error leyendo CSV: {state.error}")
    if not state.last_row:
        return _fail("CSV vacio")
    vehicle = state.last_row.get("vehicle_id", "?")
    speed = state.last_row.get("speed_kmh", "?")
    _ok(f"Ultima fila: vehicle_id={vehicle} speed_kmh={speed}")
    missing = required_fields_present({k: v for k, v in state.last_row.items() if v})
    if missing:
        return _fail(f"Faltan campos obligatorios en CSV: {missing}")
    _ok("Campos obligatorios presentes en ultima fila")
    return 0


def check_api_endpoints() -> int:
    print("\n--- API (logic) ---")
    code = 0

    health_body = health_payload()
    if health_body.get("status") != "ok":
        code = _fail(f"/v1/health -> status={health_body.get('status')!r}")
    else:
        _ok("/v1/health")

    status_body = status_payload()
    if status_body.get("schema_version") != "status_v1":
        code = _fail("/v1/status -> schema_version invalido")
    else:
        _ok(
            f"/v1/status agent_mode={status_body.get('agent_mode')} "
            f"probe_ok={status_body.get('probe_ok')}"
        )
        if status_body.get("csv_found"):
            print(
                f"       vehicle={status_body.get('vehicle_ce_id')} "
                f"mod={status_body.get('vehicle_mod_id')}"
            )
        age_s = status_body.get("csv_age_s")
        if isinstance(age_s, (int, float)) and age_s > 86400:
            _warn(f"CSV antiguo ({age_s / 3600:.1f} h) — graba de nuevo con grabar_ce.py")

    try:
        body = read_sample_payload()
    except SampleReadError as exc:
        code = _fail(f"/v1/sample -> {exc.status_code} {exc.detail}")
    else:
        if body.get("schema_version") != "ce_sample_v1":
            code = _fail("schema_version != ce_sample_v1")
        else:
            _ok("/v1/sample ce_sample_v1")
            print(
                "       "
                + json.dumps(
                    {
                        "vehicle_id": body.get("vehicle_id"),
                        "speed_kmh": body.get("speed_kmh"),
                        "terrain_kind": body.get("terrain_kind"),
                        "map_name": body.get("map_name"),
                    },
                    ensure_ascii=False,
                )
            )
    return code


def check_http_routes() -> int:
    """Rutas FastAPI via TestClient (sin levantar uvicorn)."""
    print("\n--- API (HTTP TestClient) ---")
    try:
        from fastapi.testclient import TestClient

        from snowrunner_telemetry_api.main import app
    except ImportError as exc:
        return _fail(f"fastapi no disponible: {exc}")

    client = TestClient(app)
    code = 0

    root = client.get("/")
    if root.status_code != 200 or root.json().get("name") != "SnowRunner Telemetry API":
        code = _fail(f"GET / -> {root.status_code}")
    else:
        _ok("GET / indice")

    health = client.get("/v1/health")
    if health.status_code != 200 or health.json().get("status") != "ok":
        code = _fail(f"GET /v1/health -> {health.status_code}")
    else:
        _ok("GET /v1/health")

    status = client.get("/v1/status")
    if status.status_code != 200:
        code = _fail(f"GET /v1/status -> {status.status_code}")
    else:
        _ok("GET /v1/status")

    sample = client.get("/v1/sample")
    if sample.status_code != 200:
        code = _fail(f"GET /v1/sample -> {sample.status_code} {sample.text[:120]}")
    else:
        _ok("GET /v1/sample")

    return code


def main() -> int:
    print("Fase 1 - comprobacion snowrunner-telemetry-api")
    code = check_csv()
    code = check_api_endpoints() or code
    code = check_http_routes() or code
    print()
    if code == 0:
        print("RESULTADO: Fase 1 OK - puedes arrancar con: python -m snowrunner_telemetry_api")
    else:
        print("RESULTADO: hay fallos - revisa arriba antes de seguir a Fase 2")
    return code


if __name__ == "__main__":
    sys.exit(main())
