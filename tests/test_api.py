from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from snowrunner_telemetry_api.main import app

FIXTURE_CSV = Path(__file__).resolve().parents[1] / "fixtures" / "ce_log_snippet.csv"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("SNOWRUNNER_CSV_PATH", str(FIXTURE_CSV))
    return TestClient(app)


def test_health(client: TestClient) -> None:
    response = client.get("/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["agent_mode"] == "csv"


def test_status_with_fixture_csv(client: TestClient) -> None:
    response = client.get("/v1/status")
    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "status_v1"
    assert body["agent_mode"] == "csv"
    assert body["csv_found"] is True
    assert body["csv_row_count"] == 2
    assert body["vehicle_ce_id"] == "s_krs_58_bandit"
    assert body["vehicle_mod_id"] == "bandit"
    assert body["probe_ok"] is True


def test_sample_returns_ce_sample_v1(client: TestClient) -> None:
    response = client.get("/v1/sample")
    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "ce_sample_v1"
    assert body["vehicle_id"] == "s_krs_58_bandit"
    assert body["vehicle_mod_id"] == "bandit"
    assert body["source"] == "csv"
    assert body["speed_kmh"] == pytest.approx(5.66)
    assert body["map_name"] == "Black River"


def test_sample_csv_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SNOWRUNNER_CSV_PATH", str(Path("/nonexistent/telemetria_ce_log.csv")))
    client = TestClient(app)
    response = client.get("/v1/sample")
    assert response.status_code == 404
