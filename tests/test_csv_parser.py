from __future__ import annotations

from pathlib import Path

import pytest

from snowrunner_telemetry_api.csv_source import read_last_row
from snowrunner_telemetry_api.registry import vehicle_mod_id
from snowrunner_telemetry_api.sample import csv_row_to_sample, required_fields_present

FIXTURE_CSV = Path(__file__).resolve().parents[1] / "fixtures" / "ce_log_snippet.csv"


def test_read_last_row_from_fixture() -> None:
    state = read_last_row(FIXTURE_CSV)
    assert state.exists
    assert state.readable
    assert state.error is None
    assert state.row_count == 2
    assert state.last_row is not None
    assert state.last_row["vehicle_id"] == "s_krs_58_bandit"
    assert float(state.last_row["speed_kmh"]) == pytest.approx(5.66)


def test_csv_row_to_sample_with_throttle_input() -> None:
    state = read_last_row(FIXTURE_CSV)
    assert state.last_row
    sample = csv_row_to_sample(state.last_row)
    assert sample["schema_version"] == "ce_sample_v1"
    assert sample["vehicle_id"] == "s_krs_58_bandit"
    assert sample["speed_kmh"] == pytest.approx(5.66)
    assert sample["throttle"] == pytest.approx(0.85)
    assert sample["throttle_input"] == pytest.approx(0.85)
    assert sample["engine_rpm"] == pytest.approx(1200.0)
    assert not required_fields_present(sample)


def test_legacy_throttle_fallback_without_input_column() -> None:
    row = {
        "t_s": "1.0",
        "speed_kmh": "10",
        "vehicle_id": "s_krs_58_bandit",
        "terrain_kind": "hard",
        "chain": "TRUCK_CONTROL",
        "throttle": "0.72",
    }
    sample = csv_row_to_sample(row)
    assert sample["throttle_input"] == pytest.approx(0.72)
    assert sample["throttle"] == pytest.approx(0.72)
    assert sample.get("throttle_input_legacy_fallback") is True


def test_legacy_throttle_minus_one_not_used_as_input() -> None:
    row = {
        "t_s": "1.0",
        "speed_kmh": "40",
        "vehicle_id": "s_krs_58_bandit",
        "terrain_kind": "hard",
        "chain": "TRUCK_CONTROL",
        "throttle": "-1",
        "throttle_motor": "0.5",
    }
    sample = csv_row_to_sample(row)
    assert "throttle_input" not in sample
    assert sample["throttle"] == pytest.approx(0.5)
    assert sample["throttle_motor"] == pytest.approx(0.5)


def test_vehicle_mod_id_mapping() -> None:
    assert vehicle_mod_id("s_krs_58_bandit") == "bandit"
    assert vehicle_mod_id("s_fleetstar_f2070a") == "fleetstar"
    assert vehicle_mod_id("unknown_truck") is None
