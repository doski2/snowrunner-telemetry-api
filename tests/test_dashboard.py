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


def test_build_view_full_sample(tmp_path):
    from snowrunner_telemetry_api.dashboard.advice import IdealThrottleTable
    from snowrunner_telemetry_api.dashboard.view import build_view

    sample = {
        "vehicle_id": "s_krs_58_bandit",
        "throttle_game": 0.5,
        "fuel_pct": 69.0,
        "fuel_liters": 144.86,
        "fuel_cap_liters": 210,
        "terrain_kind": "mud",
        "mud_grade_label": "mud_deep",
        "wheel_grip": 0.6,
        "surface_avg": 0.9,
        "wheel_count": 8,
        "fuel_source": "ce_fuel_hud",
    }
    view = build_view(sample, 12.34, IdealThrottleTable(tmp_path / "no_existe.json"))
    assert view.speed_text == "12.3"
    assert view.gas_pct == 50.0 and view.gas_text == "50 %"
    assert view.fuel_text == "69 %  ·  145 / 210 L"
    assert view.terrain_title == "MUD (mud deep)"
    assert view.terrain_detail == "grip 0.60 · surface 0.90 · 8 ruedas"
    assert "sin datos" in view.gas_advice
    assert view.vehicle == "s_krs_58_bandit" and view.source == "ce_fuel_hud"


def test_build_view_empty_sample(tmp_path):
    from snowrunner_telemetry_api.dashboard.advice import IdealThrottleTable
    from snowrunner_telemetry_api.dashboard.view import build_view

    view = build_view({}, 0.0, IdealThrottleTable(tmp_path / "x.json"))
    assert view.gas_pct is None and view.gas_text == "—"
    assert view.fuel_text == "—" and view.fuel_pct is None
    assert view.terrain_title == "—" and view.vehicle == "—"


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


def test_agent_source_publishes_every_sample_to_callback():
    from snowrunner_telemetry_api.dashboard.agent_source import AgentLoopSource

    seen: list[int] = []
    source = AgentLoopSource(500, on_sample=lambda s: seen.append(s["sample_seq"]))
    for seq in (1, 2, 3):  # la ventana solo consultaría la última, el callback recibe todas
        source._publish({"sample_seq": seq, "speed_kmh": float(seq)})
    assert seen == [1, 2, 3]
    assert source.latest()["sample_seq"] == 3


def test_agent_source_callback_error_does_not_break_reader():
    from snowrunner_telemetry_api.dashboard.agent_source import AgentLoopSource

    def boom(_sample):
        raise RuntimeError("disco lleno")

    source = AgentLoopSource(500, on_sample=boom)
    source._publish({"sample_seq": 1, "speed_kmh": 5.0})
    assert source.latest()["speed_kmh"] == 5.0


def test_efficiency_advice_in_view(tmp_path):
    import json

    from snowrunner_telemetry_api.dashboard.advice import EfficiencyTable, IdealThrottleTable
    from snowrunner_telemetry_api.dashboard.view import build_view

    eff = tmp_path / "e.json"
    eff.write_text(json.dumps({"s_x": {"mud|carga=vacio": {
        "most_efficient": [0.5, 0.75], "best_l_per_100km": 38.2,
        "full_throttle_extra_pct": 35, "confidence": "baja"}}}))
    table = EfficiencyTable(eff)
    sample = {"vehicle_id": "s_x", "terrain_kind": "mud", "throttle_game": 0.6}
    view = build_view(sample, 5.0, IdealThrottleTable(tmp_path / "n.json"), None, table, {"carga": "vacio"})
    assert view.efficiency_advice == "eficiente 50–75 % (~38 L/100 km) · a fondo +35 % · datos escasos"
    # otro contexto -> sin consejo (no mezclar situaciones distintas)
    other = build_view(sample, 5.0, IdealThrottleTable(tmp_path / "n.json"), None, table, {"carga": "bastidor"})
    assert other.efficiency_advice == ""
