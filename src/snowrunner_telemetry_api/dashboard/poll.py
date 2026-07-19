"""Fuentes de muestra para el dashboard — API HTTP o agente C#."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from snowrunner_telemetry_api.config import DEFAULT_HOST, api_port
from snowrunner_telemetry_api.platform_win import snowrunner_running


class ApiSampleError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def api_base_url() -> str:
    raw = os.environ.get("SNOWRUNNER_API_URL", "").strip()
    if raw:
        return raw.rstrip("/")
    host = os.environ.get("SNOWRUNNER_API_HOST", DEFAULT_HOST).strip() or DEFAULT_HOST
    return f"http://{host}:{api_port()}"


def fetch_json(url: str, timeout: float = 2.0) -> dict[str, Any]:
    try:
        with urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode())
    except HTTPError as exc:
        detail = _http_error_detail(exc)
        raise ApiSampleError(_format_http_error(exc.code, detail), status_code=exc.code) from exc


def _http_error_detail(exc: HTTPError) -> Any:
    try:
        body = exc.read().decode(errors="replace")
    except OSError:
        return exc.reason
    if not body:
        return exc.reason
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return body
    if isinstance(parsed, dict) and "detail" in parsed:
        return parsed["detail"]
    return parsed


def _format_http_error(code: int, detail: Any) -> str:
    if code == 404 and detail == "csv_not_found":
        return "CSV no encontrado — activa grabar_ce.py o usa --source agent"
    if code == 404 and detail == "csv_empty":
        return "CSV vacío — esperando grabación"
    if code == 503:
        return f"CSV no legible ({detail})"
    return f"HTTP {code}: {detail}"


def parse_speed_kmh(sample: dict[str, Any]) -> float:
    raw = sample.get("speed_kmh")
    if raw is None or raw == "":
        raise ValueError("speed_kmh ausente")
    return float(raw)


def parse_optional_float(sample: dict[str, Any], key: str) -> float | None:
    raw = sample.get(key)
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _csv_is_live(status: dict[str, Any], *, max_age_s: float = 3.0) -> bool:
    if not status.get("csv_found"):
        return False
    age = status.get("csv_age_s")
    if age is None:
        return False
    try:
        return float(age) <= max_age_s
    except (TypeError, ValueError):
        return False


def resolve_source(mode: str, base_url: str) -> str:
    if mode in ("api", "agent"):
        return mode

    # Con el juego abierto, el CSV suele estar congelado (sin grabar_ce.py).
    if snowrunner_running():
        return "agent"

    try:
        status = fetch_json(f"{base_url}/v1/status", timeout=1.0)
        if _csv_is_live(status):
            sample = fetch_json(f"{base_url}/v1/sample", timeout=1.0)
            parse_speed_kmh(sample)
            return "api"
    except (ApiSampleError, URLError, OSError, ValueError, TimeoutError):
        pass

    try:
        fetch_json(f"{base_url}/v1/health", timeout=1.0)
        sample = fetch_json(f"{base_url}/v1/sample", timeout=1.0)
        parse_speed_kmh(sample)
        return "api"
    except (ApiSampleError, URLError, OSError, ValueError, TimeoutError):
        return "agent"


def fetch_api_sample(base_url: str) -> dict[str, Any]:
    try:
        return fetch_json(f"{base_url}/v1/sample")
    except URLError as exc:
        raise ApiSampleError(
            f"Sin API ({exc.reason}) — arranca .\\run_api.bat o usa --source agent"
        ) from exc
    except OSError as exc:
        raise ApiSampleError(str(exc)) from exc
