import math

import pytest

from snowrunner_telemetry_api import physics as P


def _rot(pitch_deg: float, yaw_deg: float = 0.0, fwd_col: int = 2):
    """Matriz con el eje delantero en la columna `fwd_col`, con cabeceo y guiñada dados (Y arriba)."""
    p, y = math.radians(pitch_deg), math.radians(yaw_deg)
    fwd = (math.cos(p) * math.sin(y), math.sin(p), math.cos(p) * math.cos(y))
    up = (-math.sin(p) * math.sin(y), math.cos(p), -math.sin(p) * math.cos(y))
    right = P._cross(up, fwd)
    free = [i for i in range(3) if i != fwd_col]
    by_col = {fwd_col: fwd, free[0]: up, free[1]: right}
    return [c for i in range(3) for c in by_col[i]]


def _sample(rot, speed_ms, pitch_deg, t=0.0, yaw_rate=0.0, **extra):
    p = math.radians(pitch_deg)
    return {
        "rot": rot, "t": t,
        "vel": {"x": 0.0, "y": speed_ms * math.sin(p), "z": speed_ms * math.cos(p)},
        "ang_vel": [0.0, yaw_rate, 0.0], "speed_kmh": speed_ms * 3.6, **extra,
    }


@pytest.mark.parametrize("fwd_col", [0, 1, 2])
def test_forward_axis_detected_for_any_column(fwd_col):
    rows = [_sample(_rot(5, fwd_col=fwd_col), 5.0, 5) for _ in range(30)]
    assert P.detect_forward_axis(rows) == (fwd_col, 1)


def test_forward_axis_sign_when_reversing():
    rows = [_sample(_rot(0), -4.0, 0) for _ in range(30)]
    assert P.detect_forward_axis(rows) == (2, -1)


def test_forward_axis_needs_enough_moving_samples():
    assert P.detect_forward_axis([_sample(_rot(0), 0.2, 0) for _ in range(40)]) is None
    assert P.detect_forward_axis([_sample(_rot(0), 5.0, 0) for _ in range(5)]) is None


def test_pose_pitch_and_slope():
    p = P.pose(_sample(_rot(10), 5.0, 10), (2, 1))
    assert p["pitch_deg"] == pytest.approx(10, abs=1e-6)
    assert p["slope_pct"] == pytest.approx(math.tan(math.radians(10)) * 100, abs=1e-6)
    assert p["v_long_ms"] == pytest.approx(5.0, abs=1e-6)
    assert P.pose(_sample(_rot(-6), 5.0, -6), (2, 1))["pitch_deg"] == pytest.approx(-6, abs=1e-6)


def test_net_accel_adds_gravity_component_uphill():
    # En una subida de 10° una aceleración medida de 0 m/s² exige G·sen(10°) del motor
    assert P.net_drive_accel(0.0, 10.0) == pytest.approx(P.G * math.sin(math.radians(10)))
    assert P.net_drive_accel(1.0, -10.0) < 1.0  # en bajada el motor aporta menos


def test_lateral_g():
    assert P.lateral_g(10.0, 0.5) == pytest.approx(5.0 / P.G)


def test_live_metrics_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "AXIS_PRIOR_PATH", tmp_path / "axis.json")
    live = P.LiveMetrics()
    live.axis = None
    out = {}
    for i in range(60):
        s = _sample(_rot(8), 5.0 + 0.5 * i * 0.1, 8, pos=[0.0, 0.0, i * 0.5],
                    fuel_liters=100.0 - i * 0.01, vehicle_id="s_x", yaw_rate=0.2)
        out = live.update(s, t=i * 0.1)
    assert live.axis == (2, 1) and P.load_axis_prior() == (2, 1)
    assert out["pitch_deg"] == pytest.approx(8, abs=1e-6)
    assert out["a_long_ms2"] == pytest.approx(0.5, abs=0.05)
    assert out["a_net_ms2"] > out["a_long_ms2"]
    assert out["distance_m"] == pytest.approx(59 * 0.5)
    assert out["lat_g"] > 0
    assert out["fuel_l_per_h"] == pytest.approx(0.01 / 0.1 * 3600, rel=0.05)
    assert out["fuel_l_per_100km"] > 0


def test_live_metrics_resets_on_vehicle_change_and_ignores_teleport(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "AXIS_PRIOR_PATH", tmp_path / "a.json")
    live = P.LiveMetrics()
    live.update({"vehicle_id": "a", "pos": [0, 0, 0]}, 0.0)
    live.update({"vehicle_id": "a", "pos": [3, 0, 4]}, 0.1)
    assert live.distance_m == pytest.approx(5.0)
    live.update({"vehicle_id": "a", "pos": [900, 0, 0]}, 0.2)  # salto: no suma
    assert live.distance_m == pytest.approx(5.0)
    live.update({"vehicle_id": "b", "pos": [0, 0, 0]}, 0.3)
    assert live.distance_m == 0.0


def test_axis_is_reverified_for_each_vehicle(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "AXIS_PRIOR_PATH", tmp_path / "axis.json")
    live = P.LiveMetrics()
    live.axis = (2, 1)  # a priori guardado
    for i in range(30):  # el camión "a" tiene el eje delantero en la columna 0
        live.update(_sample(_rot(0, fwd_col=0), 5.0, 0, vehicle_id="a"), t=i * 0.1)
    assert live.axis == (0, 1)
    for i in range(30):  # otro camión con la convención distinta
        live.update(_sample(_rot(0, fwd_col=1), 5.0, 0, vehicle_id="b"), t=i * 0.1)
    assert live.axis == (1, 1)


def test_live_metrics_uses_prior_until_verified(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "AXIS_PRIOR_PATH", tmp_path / "axis.json")
    live = P.LiveMetrics()
    live.axis = (2, 1)
    out = live.update(_sample(_rot(7), 4.0, 7, vehicle_id="a"), t=0.0)
    assert out["pitch_deg"] == pytest.approx(7, abs=1e-6)  # ya hay cabeceo antes de verificar
