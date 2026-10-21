import gzip
import json

import pytest

from snowrunner_telemetry_api import physics
from snowrunner_telemetry_api.analysis import compress_session, load_meta, load_rows, session_files
from snowrunner_telemetry_api.autorecord import PlayRecorder
from snowrunner_telemetry_api.context import ContextTags
from snowrunner_telemetry_api.coverage import CoverageTracker, gas_bin, human_bin
from snowrunner_telemetry_api.dashboard.recorder import SLIM_FIELDS, SessionRecorder


@pytest.fixture(autouse=True)
def _no_axis_prior(monkeypatch, tmp_path):
    monkeypatch.setattr(physics, "AXIS_PRIOR_PATH", tmp_path / "no_axis.json")


def _sample(i, gas=0.6, terrain="mud", vehicle="s_x", dt_ms=100, **extra):
    return {"sample_seq": i, "ts_ms": 1000.0 + i * dt_ms, "vehicle_id": vehicle,
            "throttle_game": gas, "terrain_kind": terrain, "speed_kmh": 5.0, **extra}


def test_gas_bin_and_human_labels():
    assert gas_bin(0.02) is None and gas_bin(None) is None
    assert gas_bin(0.6) == "0.50-0.75" and gas_bin(1.0) == "0.95-1.00"
    assert human_bin("0.50-0.75") == "50–75 %" and human_bin("0.95-1.00") == "≥95 %"


def test_coverage_accumulates_time_per_bin_and_reports_missing(tmp_path):
    cov = CoverageTracker(tmp_path / "c.json", target_s=10.0)
    ctx = {"carga": "vacio"}
    for i in range(101):  # 10 s a gas medio
        cov.update(_sample(i, 0.6), ctx, now=0.0)
    st = cov.status("s_x", "mud", ctx)
    assert st.seconds_by_bin["0.50-0.75"] == pytest.approx(10.0, abs=0.01)
    assert st.percent == pytest.approx(20.0, abs=0.1)  # 1 de 5 tramos completo
    assert "0.50-0.75" not in st.missing and len(st.missing) == 4
    assert "falta gas" in cov.hint("s_x", "mud", ctx) and "20 % completo" in cov.hint("s_x", "mud", ctx)
    # otra etiqueta = otra situación, sin mezclar
    assert cov.status("s_x", "mud", {"carga": "bastidor"}).percent == 0.0


def test_coverage_ignores_gaps_idle_and_vehicle_change(tmp_path):
    cov = CoverageTracker(tmp_path / "c.json", target_s=10.0)
    cov.update(_sample(0, 0.6), None, 0.0)
    cov.update(_sample(1, 0.6, dt_ms=5000), None, 0.0)  # hueco de 5 s: no cuenta
    cov.update(_sample(2, 0.01), None, 0.0)  # gas ~0: no es una situación
    cov.update(_sample(3, 0.6, vehicle="s_y"), None, 0.0)  # cambio de camión: reinicia el reloj
    assert cov.status("s_x", "mud", None).total_seconds == 0.0


def test_coverage_persists_and_rebuilds_from_rows(tmp_path):
    path = tmp_path / "c.json"
    cov = CoverageTracker(path, target_s=10.0)
    rows = [{**_sample(i, 0.6), "t": i * 0.1, "ctx": {"carga": "vacio"}} for i in range(51)]
    cov.add_rows(rows)
    cov.save()
    again = CoverageTracker(path, target_s=10.0)
    assert again.status("s_x", "mud", {"carga": "vacio"}).total_seconds == pytest.approx(5.0, abs=0.01)
    again.reset()
    assert again.status("s_x", "mud", {"carga": "vacio"}).total_seconds == 0.0


def test_slimmer_rows_keep_only_analysis_fields(tmp_path):
    rec = SessionRecorder("s", tmp_path, fields=SLIM_FIELDS)
    rec.write({"sample_seq": 1, "speed_kmh": 3.0, "throttle_game": 0.5, "xinput_rt": 9,
               "physical_input_raw": 123, "terrain_source": "wheel_model:...", "rot": [0] * 9})
    rec.close()
    row = load_rows(rec.path)[0]
    assert "xinput_rt" not in row and "terrain_source" not in row and "label" not in row
    assert row["throttle_game"] == 0.5 and row["rot"] == [0] * 9


def test_compressed_sessions_are_read_transparently(tmp_path):
    rec = SessionRecorder("g", tmp_path, meta={"initial_pak": {"sha1": "abc"}})
    for i in range(20):
        rec.write({"sample_seq": i, "speed_kmh": float(i)})
    rec.close()
    gz = compress_session(rec.path)
    assert gz.suffix == ".gz" and not rec.path.exists()
    assert [p.name for p in session_files(tmp_path)] == [gz.name]
    assert len(load_rows(gz)) == 20 and load_meta(gz)["initial_pak"]["sha1"] == "abc"
    with gzip.open(gz, "rt", encoding="utf-8") as fh:
        assert json.loads(fh.readline())["_meta"]


def _play(tmp_path, **kw):
    cov = CoverageTracker(tmp_path / "c.json", target_s=60.0)
    return PlayRecorder(tmp_path, interval_ms=100, coverage=cov, **kw), cov


def test_play_recorder_counts_coverage_and_writes_slim_rows(tmp_path):
    rec, cov = _play(tmp_path)
    for i in range(30):
        rec.handle(_sample(i, 0.6, xinput_rt=1), now=i * 0.1)
    rec.close()
    assert rec.rows == 30
    assert cov.status("s_x", "mud", None).total_seconds == pytest.approx(2.9, abs=0.01)
    assert "xinput_rt" not in load_rows(next(tmp_path.glob("*.ndjson")))[0]


def test_cap_thins_covered_situations_but_not_new_ones(tmp_path):
    rec, cov = _play(tmp_path, cap_seconds=3.0, keep_ratio=5)
    for i in range(100):  # 10 s en la misma situación: tras 3 s se aligera a 1 de cada 5
        rec.handle(_sample(i, 0.6), now=i * 0.1)
    full_rate = 31  # ≈ hasta 3 s a ritmo completo
    assert full_rate <= rec.rows <= full_rate + 15 and rec.skipped_capped > 40
    before = rec.rows
    for i in range(100, 110):  # otro terreno: situación nueva -> ritmo completo
        rec.handle(_sample(i, 0.6, terrain="hard"), now=i * 0.1)
    assert rec.rows == before + 10
    rec.close()


def test_no_cap_by_default_records_everything(tmp_path):
    rec, _ = _play(tmp_path)
    for i in range(200):
        rec.handle(_sample(i, 0.6), now=i * 0.1)
    assert rec.rows == 200 and rec.skipped_capped == 0
    rec.close()


def test_cap_separates_slope_bands(tmp_path, monkeypatch):
    monkeypatch.setattr(physics, "load_axis_prior", lambda: (2, 1))
    rec, cov = _play(tmp_path, cap_seconds=2.0, keep_ratio=5)
    import math

    def rot(pitch):  # eje delantero en la columna 2
        p = math.radians(pitch)
        return [1, 0, 0, 0, math.cos(p), -math.sin(p), 0, math.sin(p), math.cos(p)]

    for i in range(60):  # 6 s en llano: se aligera
        rec.handle(_sample(i, 0.6, rot=rot(0), vel={"x": 0, "y": 0, "z": 1}), now=i * 0.1)
    flat_rows = rec.rows
    for i in range(60, 75):  # subida (15°) durante 1,5 s (< tope): situación distinta -> ritmo completo
        rec.handle(_sample(i, 0.6, rot=rot(15), vel={"x": 0, "y": 0, "z": 1}), now=i * 0.1)
    assert rec.rows == flat_rows + 15
    rec.close()


def test_play_recorder_context_goes_in_rows(tmp_path):
    tags = ContextTags(tmp_path / "ctx.json")
    tags.update({"carga": "vacio"})
    rec, _ = _play(tmp_path, context=tags)
    rec.handle(_sample(1), now=0.0)
    rec.close()
    assert load_rows(next(tmp_path.glob("*.ndjson")))[0]["ctx"] == {"carga": "vacio"}
