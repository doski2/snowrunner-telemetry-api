import pytest

from snowrunner_telemetry_api.analysis import analyze, compare_targets, load_rows
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


def _eff_session(plan, ctx=None, terrain="mud", reps=1):
    """plan: [(gas, m/s, L/s)] — 12 s por tramo a 10 Hz, avanzando en línea recta."""
    rows, t, z, fuel = [], 0.0, 0.0, 100.0
    for gas, speed, burn in plan:
        for _ in range(120 * reps):
            rows.append({"t": round(t, 2), "speed_kmh": speed * 3.6, "throttle_game": gas,
                         "terrain_kind": terrain, "fuel_liters": fuel, "pos": [0.0, 0.0, z],
                         "vehicle_id": "s_x", **({"ctx": ctx} if ctx else {})})
            t += 0.1
            z += speed * 0.1
            fuel -= burn * 0.1
    return rows


def test_efficiency_picks_lowest_l_per_100km_not_lowest_l_per_h():
    from snowrunner_telemetry_api.analysis import efficiency_report

    # poco gas: gasta menos por hora pero avanza muy poco -> peor por distancia
    rows = _eff_session([(0.15, 0.5, 0.004), (0.4, 3.0, 0.006), (0.6, 4.0, 0.0085), (0.85, 4.5, 0.012), (1.0, 4.6, 0.02)], reps=6)
    entry = efficiency_report([rows])["mud|sin etiqueta"]
    assert entry["most_efficient"] == [0.25, 0.5]
    assert entry["bins"]["0.05-0.25"]["l_per_100km"] > entry["bins"]["0.25-0.50"]["l_per_100km"]
    assert entry["full_throttle_extra_pct"] > 100
    assert entry["missing_bins"] == []  # hay tiempo en todos los tramos, aunque el 1.º apenas avance
    assert entry["confidence"] == "alta"


def test_efficiency_separates_context_and_reports_missing_bins():
    from snowrunner_telemetry_api.analysis import efficiency_report

    vacio = _eff_session([(0.6, 4.0, 0.008), (1.0, 4.6, 0.016)], ctx={"carga": "vacio"})
    carga = _eff_session([(0.6, 3.0, 0.010)], ctx={"carga": "bastidor"})
    report = efficiency_report([vacio, carga])
    assert set(report) == {"mud|carga=vacio", "mud|carga=bastidor"}
    assert report["mud|carga=bastidor"]["confidence"] == "baja"
    assert "0.05-0.25" in report["mud|carga=vacio"]["missing_bins"]


def test_efficiency_ignores_refuel_and_gaps():
    from snowrunner_telemetry_api.analysis import efficiency_report

    rows = _eff_session([(0.6, 4.0, 0.008)])
    for r in rows[60:]:
        r["fuel_liters"] += 50  # repostaje a mitad: ese intervalo no debe contar
    entry = efficiency_report([rows])["mud|sin etiqueta"]
    assert entry["bins"]["0.50-0.75"]["liters"] < 1.0


def test_context_tags_roundtrip_and_hot_reload(tmp_path):
    from snowrunner_telemetry_api.context import ContextTags, parse_pairs, signature

    tags = ContextTags(tmp_path / "c.json")
    assert tags.current() == {} and signature({}) == "sin etiqueta"
    tags.update(parse_pairs(["carga=vacio", "neumaticos = Ultima AT I"]))
    assert tags.current() == {"carga": "vacio", "neumaticos": "Ultima AT I"}
    assert signature(tags.current()) == "carga=vacio, neumaticos=Ultima AT I"
    tags.unset(["carga"])
    assert tags.current() == {"neumaticos": "Ultima AT I"}
    with pytest.raises(ValueError):
        parse_pairs(["sin_igual"])


def test_recorder_writes_context_per_row(tmp_path):
    from snowrunner_telemetry_api.context import ContextTags
    from snowrunner_telemetry_api.dashboard.recorder import SessionRecorder

    tags = ContextTags(tmp_path / "c.json")
    rec = SessionRecorder("x", tmp_path, context=tags)
    rec.write({"sample_seq": 1, "speed_kmh": 1})
    tags.update({"carga": "bastidor"})  # cambio en caliente
    rec.write({"sample_seq": 2, "speed_kmh": 2})
    rec.close()
    rows = load_rows(rec.path)
    assert "ctx" not in rows[0] and rows[1]["ctx"] == {"carga": "bastidor"}


def test_efficiency_reports_slip_per_gas_bin():
    from snowrunner_telemetry_api.analysis import efficiency_report

    rows = _eff_session([(0.6, 4.0, 0.0085), (1.0, 4.6, 0.02)], reps=2)
    for r in rows:  # a fondo patina el 40 %; a gas medio, 5 %
        r["slip_mean"] = 0.4 if r["throttle_game"] >= 0.95 else 0.05
    e = efficiency_report([rows])["mud|sin etiqueta"]
    assert e["bins"]["0.95-1.00"]["mean_slip"] == 0.4 and e["bins"]["0.95-1.00"]["high_slip_share"] == 1.0
    assert e["bins"]["0.50-0.75"]["mean_slip"] == 0.05 and e["bins"]["0.50-0.75"]["high_slip_share"] == 0.0


def test_efficiency_prefers_raw_fuel_and_flags_modelled_fuel():
    from snowrunner_telemetry_api.analysis import efficiency_report

    modelled = _eff_session([(0.6, 4.0, 0.0085)], reps=2)
    assert efficiency_report([modelled])["mud|sin etiqueta"]["fuel_basis"] == "modelo"

    direct = _eff_session([(0.6, 4.0, 0.0085)], reps=2)
    for r in direct:  # el valor interpolado miente (no baja); el directo es el real
        r["fuel_liters_raw"] = r["fuel_liters"]
        r["fuel_liters"] = 100.0
    e = efficiency_report([direct])["mud|sin etiqueta"]
    assert e["fuel_basis"] == "memoria"
    assert e["bins"]["0.50-0.75"]["liters"] == pytest.approx(0.204, abs=0.01)  # el directo; el interpolado daría 0
