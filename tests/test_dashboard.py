"""Tests del módulo dashboard (sin abrir GUI)."""

from __future__ import annotations

import pytest

from snowrunner_telemetry_api.dashboard.poll import (
    ApiSampleError,
    _format_http_error,
    api_base_url,
    parse_speed_kmh,
    resolve_source,
)


def test_api_base_url_default(monkeypatch):
    monkeypatch.delenv("SNOWRUNNER_API_URL", raising=False)
    monkeypatch.delenv("SNOWRUNNER_API_HOST", raising=False)
    monkeypatch.delenv("SNOWRUNNER_API_PORT", raising=False)
    assert api_base_url() == "http://127.0.0.1:8765"


def test_api_base_url_override(monkeypatch):
    monkeypatch.setenv("SNOWRUNNER_API_URL", "http://localhost:9000/")
    assert api_base_url() == "http://localhost:9000"


def test_parse_speed_kmh():
    assert parse_speed_kmh({"speed_kmh": 12.5}) == 12.5
    assert parse_speed_kmh({"speed_kmh": "3.2"}) == 3.2


def test_parse_speed_kmh_missing():
    with pytest.raises(ValueError):
        parse_speed_kmh({})


def test_parse_optional_float_fuel():
    from snowrunner_telemetry_api.dashboard.poll import parse_optional_float

    assert parse_optional_float({"fuel_pct": 72.5}, "fuel_pct") == 72.5
    assert parse_optional_float({"fuel_pct": "80"}, "fuel_pct") == 80.0
    assert parse_optional_float({}, "fuel_pct") is None


def test_normalize_chart_metric():
    from snowrunner_telemetry_api.dashboard.metrics import normalize_chart_metric

    assert normalize_chart_metric("fuel_pct") == "fuel_pct"
    assert normalize_chart_metric("Combustible") == "fuel_pct"
    assert normalize_chart_metric("invalid") == "speed_kmh"


def test_format_http_error_csv_not_found():
    msg = _format_http_error(404, "csv_not_found")
    assert "CSV no encontrado" in msg
    assert "agent" in msg


def test_resolve_source_api(monkeypatch):
    calls: list[str] = []

    def fake_fetch(url: str, timeout: float = 2.0):
        calls.append(url)
        if url.endswith("/v1/health"):
            return {"status": "ok"}
        if url.endswith("/v1/status"):
            return {"csv_found": True, "csv_age_s": 1.0}
        return {"speed_kmh": 10.0, "vehicle_id": "s_test"}

    monkeypatch.setattr(
        "snowrunner_telemetry_api.dashboard.poll.snowrunner_running",
        lambda: False,
    )
    monkeypatch.setattr(
        "snowrunner_telemetry_api.dashboard.poll.fetch_json",
        fake_fetch,
    )
    assert resolve_source("auto", "http://127.0.0.1:8765") == "api"
    assert calls[0].endswith("/v1/status")


def test_resolve_source_agent_when_game_running(monkeypatch):
    monkeypatch.setattr(
        "snowrunner_telemetry_api.dashboard.poll.snowrunner_running",
        lambda: True,
    )

    def fake_fetch(url: str, timeout: float = 2.0):
        raise AssertionError("no debe llamar API si el juego está abierto")

    monkeypatch.setattr(
        "snowrunner_telemetry_api.dashboard.poll.fetch_json",
        fake_fetch,
    )
    assert resolve_source("auto", "http://127.0.0.1:8765") == "agent"


def test_resolve_source_agent_when_csv_stale(monkeypatch):
    def fake_fetch(url: str, timeout: float = 2.0):
        if url.endswith("/v1/status"):
            return {"csv_found": True, "csv_age_s": 120.0}
        raise ApiSampleError("CSV no encontrado", status_code=404)

    monkeypatch.setattr(
        "snowrunner_telemetry_api.dashboard.poll.snowrunner_running",
        lambda: False,
    )
    monkeypatch.setattr(
        "snowrunner_telemetry_api.dashboard.poll.fetch_json",
        fake_fetch,
    )
    assert resolve_source("auto", "http://127.0.0.1:8765") == "agent"


def test_resolve_source_agent_when_api_fails(monkeypatch):
    def fake_fetch(url: str, timeout: float = 2.0):
        raise ApiSampleError("CSV no encontrado", status_code=404)

    monkeypatch.setattr(
        "snowrunner_telemetry_api.dashboard.poll.fetch_json",
        fake_fetch,
    )
    assert resolve_source("auto", "http://127.0.0.1:8765") == "agent"


def test_format_terrain_summary():
    from snowrunner_telemetry_api.dashboard.terrain import format_terrain_summary

    assert format_terrain_summary({}) == "—"
    assert "hard" in format_terrain_summary(
        {
            "terrain_kind": "hard",
            "mud_grade_label": "dry_hard",
            "wheel_grip": 0.185,
            "contact_avg": 0.765,
        }
    )


def test_compare_terrain_match():
    from snowrunner_telemetry_api.dashboard.terrain import compare_terrain

    agent = {
        "terrain_kind": "hard",
        "mud_grade_label": "dry_hard",
        "wheel_grip": 0.18,
        "contact_avg": 0.765,
    }
    api = {
        "terrain_kind": "hard",
        "mud_grade_label": "dry_hard",
        "wheel_grip": 0.185,
        "contact_avg": 0.765,
    }
    result = compare_terrain(agent, api)
    assert "[OK]" in result
    assert "hard" in result


def test_compare_terrain_mismatch():
    from snowrunner_telemetry_api.dashboard.terrain import compare_terrain

    result = compare_terrain(
        {"terrain_kind": "mud", "mud_grade_label": "mud_deep"},
        {"terrain_kind": "hard", "mud_grade_label": "dry_hard"},
    )
    assert "[REVISAR]" in result


def test_agent_source_latest():
    from snowrunner_telemetry_api.dashboard.agent_source import AgentLoopSource, AgentSampleError

    source = AgentLoopSource()
    with pytest.raises(AgentSampleError):
        source.latest()

    source._latest = {"speed_kmh": 42.0, "vehicle_id": "s_test"}
    assert source.latest()["speed_kmh"] == 42.0


def test_try_parse_json_buffer_multiline():
    from snowrunner_telemetry_api.dashboard.agent_source import try_parse_json_buffer

    lines = [
        "{",
        '  "probe_ok": true,',
        '  "speed_kmh": 12.34,',
        '  "vehicle_id": "s_fleetstar_f2070a"',
        "}",
    ]
    assert try_parse_json_buffer(lines) == {
        "probe_ok": True,
        "speed_kmh": 12.34,
        "vehicle_id": "s_fleetstar_f2070a",
    }
    assert try_parse_json_buffer(["{"]) is None
