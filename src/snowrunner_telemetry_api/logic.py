"""Lógica de API sin dependencia de FastAPI (tests, fase1_check, rutas)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .config import API_VERSION, csv_path
from .csv_source import read_last_row
from .platform_win import snowrunner_pid, snowrunner_running
from .registry import vehicle_mod_id
from .sample import SCHEMA_VERSION, csv_row_to_sample, required_fields_present


class SampleReadError(Exception):
    """Error leyendo muestra desde CSV (mapeado a HTTP en main.py)."""

    def __init__(self, status_code: int, detail: Any) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def health_payload() -> dict[str, Any]:
    return {
        "status": "ok",
        "api_version": API_VERSION,
        "agent_mode": "csv",
    }


def status_payload() -> dict[str, Any]:
    path = csv_path()
    state = read_last_row(path)
    game_running = snowrunner_running()
    pid = snowrunner_pid() if game_running else None

    vehicle_ce = (state.last_row or {}).get("vehicle_id", "")
    mod_id = vehicle_mod_id(vehicle_ce) if vehicle_ce else None

    thr_in_raw = (state.last_row or {}).get("throttle_input", "").strip()
    thr_legacy = (state.last_row or {}).get("throttle", "").strip()
    throttle_input_ok = bool(thr_in_raw) or (
        bool(thr_legacy) and thr_legacy not in ("-1", "-1.0")
    )

    last_t_s = None
    if state.last_row:
        try:
            last_t_s = float(state.last_row.get("t_s", "") or 0)
        except ValueError:
            last_t_s = None

    csv_age_s = None
    if state.last_mtime:
        csv_age_s = round(
            (datetime.now(tz=timezone.utc) - state.last_mtime).total_seconds(), 1
        )

    return {
        "schema_version": "status_v1",
        "api_ok": True,
        "api_version": API_VERSION,
        "agent_mode": "csv",
        "game_running": game_running,
        "pid": pid,
        "csv_found": state.exists,
        "csv_readable": state.readable and state.error is None,
        "csv_filename": state.filename,
        "csv_row_count": state.row_count,
        "csv_mtime_utc": state.last_mtime.isoformat() if state.last_mtime else None,
        "csv_age_s": csv_age_s,
        "csv_error": state.error,
        "vehicle_ce_id": vehicle_ce or None,
        "vehicle_mod_id": mod_id,
        "probe_ok": state.last_row is not None and state.error is None,
        "throttle_input_ok": throttle_input_ok,
        "map_name": (state.last_row or {}).get("map_name") or None,
        "level_id": (state.last_row or {}).get("level_id") or None,
        "last_sample_t_s": last_t_s,
        "samples_buffered": 1 if state.last_row else 0,
    }


def read_sample_payload() -> dict[str, Any]:
    path = csv_path()
    state = read_last_row(path)
    if not state.exists:
        raise SampleReadError(404, "csv_not_found")
    if state.error == "csv_empty" or not state.last_row:
        raise SampleReadError(404, "csv_empty")
    if state.error:
        raise SampleReadError(503, state.error)

    payload = csv_row_to_sample(state.last_row)
    missing = required_fields_present(payload)
    if missing:
        raise SampleReadError(422, {"error": "incomplete_sample", "missing": missing})

    mod = vehicle_mod_id(str(payload.get("vehicle_id", "")))
    if mod:
        payload["vehicle_mod_id"] = mod
    payload["schema_version"] = SCHEMA_VERSION
    payload["source"] = "csv"
    payload["csv_row_index"] = state.row_count
    return payload
