from snowrunner_telemetry_api.analysis import analyze, compare_targets
from snowrunner_telemetry_api.dashboard.recorder import SessionRecorder


def _rows():
    # arranca en t=2, 20 km/h a t=4, 40 a t=7; consume 0.1 L en reposo y 0.5 L en marcha
    data = [
        (0, 0.0, 100.0, "hard"),
        (1, 0.0, 99.95, "hard"),
        (2, 2.0, 99.9, "hard"),
        (4, 20.0, 99.7, "mud"),
        (7, 40.0, 99.4, "mud"),
    ]
    return [
        {"t": t, "speed_kmh": v, "fuel_liters": f, "terrain_kind": k, "vehicle_id": "s_x"}
        for t, v, f, k in data
    ]


def test_acceleration_times_from_start():
    acc = analyze(_rows())["acceleration"]
    assert acc["t_to_kmh"] == {"20": 2.0, "40": 5.0}
    assert acc["vmax_kmh"] == 40.0


def test_fuel_split_idle_and_moving():
    f = analyze(_rows())["fuel"]
    assert f["idle"]["liters"] == 0.1
    assert f["moving"]["liters"] == 0.5


def test_terrain_share_and_mud_speed():
    t = analyze(_rows())["terrain"]
    assert t["share"]["mud"] == 0.4
    assert t["mud_speed_max_kmh"] == 40.0


def test_compare_targets_reports_delta():
    lines = compare_targets(analyze(_rows()), {"t_to_kmh": {"40": 4.0, "60": 9}, "vmax_kmh": 50})
    assert "+1.00" in lines[0]
    assert "no alcanzado" in lines[1]


def _throttle_session(accel_by_gas):
    """Sesión sintética a 10 Hz: cada tramo de 12 muestras mantiene un gas con su aceleración."""
    rows, t, v = [], 0.0, 6.0
    for gas, accel in accel_by_gas:
        for _ in range(12):
            rows.append(
                {"t": round(t, 2), "speed_kmh": v, "throttle_game": gas, "terrain_kind": "mud",
                 "vehicle_id": "s_x"}
            )
            t += 0.1
            v += accel * 0.1
    return rows


def test_ideal_throttle_is_lowest_bin_near_best():
    from snowrunner_telemetry_api.analysis import ideal_throttle

    rows = _throttle_session([(0.15, 0.5), (0.4, 1.4), (0.6, 1.95), (0.9, 2.0)])
    entry = ideal_throttle([rows])["mud|5-15"]
    assert entry["ideal_throttle"] == [0.5, 0.75]
    assert entry["best_accel"] == 2.0


def test_ideal_throttle_none_when_no_gain():
    from snowrunner_telemetry_api.analysis import ideal_throttle

    rows = _throttle_session([(0.4, -0.2), (0.9, -0.1)])
    assert ideal_throttle([rows])["mud|5-15"]["ideal_throttle"] is None


def test_recorder_skips_repeated_seq(tmp_path):
    rec = SessionRecorder("prueba x", tmp_path)
    assert rec.write({"sample_seq": 1, "speed_kmh": 1})
    assert not rec.write({"sample_seq": 1, "speed_kmh": 1})
    assert rec.write({"sample_seq": 2, "speed_kmh": 2})
    rec.close()
    assert rec.count == 2
    assert rec.path.name.startswith("prueba_x_")


def test_advice_text_and_lookup(tmp_path):
    import json

    from snowrunner_telemetry_api.dashboard.advice import IdealThrottleTable, format_advice

    path = tmp_path / "t.json"
    path.write_text(json.dumps({"s_x": {"mud|5-15": {"ideal_throttle": [0.5, 0.75]}}}))
    table = IdealThrottleTable(path)
    entry = table.lookup("s_x", "mud", 8.0)
    assert entry is not None
    assert table.lookup("s_x", "hard", 8.0) is None
    assert format_advice(entry, 1.0) == "ideal 50–75 % — sobra gas"
    assert format_advice(entry, 0.2) == "ideal 50–75 % — puedes dar más"
    assert format_advice(entry, 0.6).endswith("correcto")
    assert "sin datos" in format_advice(None, 0.5)
    assert "ningún gas" in format_advice({"ideal_throttle": None}, 0.5)


def _play_rows():
    rows, t = [], 0.0
    for i in range(40):
        moving = i >= 10
        rows.append(
            {"t": round(t, 2), "speed_kmh": 20.0 if moving else 0.0,
             "throttle_game": 0.97 if moving else 0.0, "terrain_kind": "mud" if moving else "hard",
             "fuel_liters": 100.0 - i * 0.01, "vehicle_id": "s_x"}
        )
        t += 1.0
    return rows


def test_profile_report_by_terrain():
    from snowrunner_telemetry_api.analysis import profile_report

    rep = profile_report([_play_rows()])
    assert set(rep) == {"mud", "hard"}
    assert rep["mud"]["speed_p50_kmh"] == 20.0
    assert rep["mud"]["gas_full_share"] == 1.0
    assert rep["hard"]["moving_share"] == 0.0


def test_fuel_ignores_long_gaps():
    from snowrunner_telemetry_api.analysis import fuel

    rows = [
        {"t": 0, "fuel_liters": 100.0, "speed_kmh": 10},
        {"t": 100, "fuel_liters": 90.0, "speed_kmh": 10},  # hueco de 100 s: se ignora
        {"t": 101, "fuel_liters": 89.9, "speed_kmh": 10},
    ]
    assert fuel(rows)["moving"]["seconds"] == 1.0


def test_idle_thinning_and_vehicle_split(tmp_path):
    from snowrunner_telemetry_api.autorecord import PlayRecorder

    rec = PlayRecorder(tmp_path, keep_idle_s=2.0)
    idle = {"vehicle_id": "s_a", "speed_kmh": 0.0, "throttle_game": 0.0}
    kept = [rec.handle({**idle, "sample_seq": i}, now=i * 0.1) for i in range(30)]
    assert 1 < sum(kept) < 5  # ~1 cada 2 s en 3 s
    assert rec.handle({"vehicle_id": "s_a", "speed_kmh": 5.0, "sample_seq": 99}, now=4.0)
    rec.handle({"vehicle_id": "s_b", "speed_kmh": 5.0, "sample_seq": 1}, now=5.0)
    rec.close()
    names = sorted(p.name.split("_20")[0] for p in tmp_path.glob("*.ndjson"))
    assert names == ["play_s_a", "play_s_b"]


def test_meta_header_and_agent_clock(tmp_path):
    from snowrunner_telemetry_api.analysis import load_meta, load_rows
    from snowrunner_telemetry_api.dashboard.recorder import SessionRecorder

    rec = SessionRecorder("m", tmp_path, meta={"initial_pak": {"sha1": "abc"}})
    rec.write({"sample_seq": 1, "ts_ms": 5000.0, "speed_kmh": 1})
    rec.write({"sample_seq": 2, "ts_ms": 5100.0, "speed_kmh": 2})
    rec.close()
    assert load_meta(rec.path)["initial_pak"]["sha1"] == "abc"
    rows = load_rows(rec.path)
    assert len(rows) == 2 and rows[1]["t"] == 0.1  # reloj del agente, no el de lectura
