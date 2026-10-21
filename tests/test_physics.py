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


def _pose(pitch_deg: float) -> dict[str, float]:
    result = P.pose(_sample(_rot(pitch_deg), 5.0, pitch_deg), (2, 1))
    assert result is not None
    return result


def test_pose_pitch_and_slope():
    p = _pose(10)
    assert p["pitch_deg"] == pytest.approx(10, abs=1e-6)
    assert p["slope_pct"] == pytest.approx(math.tan(math.radians(10)) * 100, abs=1e-6)
    assert p["v_long_ms"] == pytest.approx(5.0, abs=1e-6)
    assert _pose(-6)["pitch_deg"] == pytest.approx(-6, abs=1e-6)


def test_pose_needs_rotation():
    assert P.pose({"vel": {"x": 0, "y": 0, "z": 1}}, (2, 1)) is None


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


def _wheel_sample(i, v, radius, slip=0.0, n=4):
    omega = v * (1 + slip) / radius
    return _sample(_rot(0), v, 0, vehicle_id="s_x", w_omega=[omega] * n, t=i * 0.1)


def test_wheel_radius_calibrates_and_slip_is_measured(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "AXIS_PRIOR_PATH", tmp_path / "a.json")
    live = P.LiveMetrics()
    live.axis = (2, 1)
    out = {}
    for i in range(80):  # rodadura limpia: calibra el radio
        out = live.update(_wheel_sample(i, 3.0, 0.44), t=i * 0.1)
    assert out["wheel_radius_m"] == pytest.approx(0.44, abs=1e-6)
    assert out["slip_mean"] == pytest.approx(0.0, abs=1e-6)
    out = live.update(_wheel_sample(81, 3.0, 0.44, slip=0.5), t=8.1)  # ruedas giran 50 % de más
    assert out["slip_mean"] == pytest.approx(0.5, abs=0.02)
    assert out["slip_max"] >= out["slip_mean"]


def test_no_slip_when_slow_or_uncalibrated(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "AXIS_PRIOR_PATH", tmp_path / "a.json")
    live = P.LiveMetrics()
    live.axis = (2, 1)
    assert "slip_mean" not in live.update(_wheel_sample(0, 3.0, 0.44), t=0.0)  # aún sin calibrar
    for i in range(80):
        live.update(_wheel_sample(i, 3.0, 0.44), t=i * 0.1)
    assert "slip_mean" not in live.update(_wheel_sample(90, 0.4, 0.44, slip=2.0), t=9.0)  # casi parado


def test_roll_positive_when_right_side_is_up():
    # adelante = +Z, arriba = +Y; en un sistema dextrógiro la derecha es adelante × arriba = (-1, 0, 0)
    th = math.radians(10)
    right = (-math.cos(th), math.sin(th), 0.0)  # costado derecho levantado 10°
    up = (math.sin(th), math.cos(th), 0.0)
    rot = [*up, *right, 0.0, 0.0, 1.0]  # columna 2 = delantera
    p = P.pose({"rot": rot, "vel": {"x": 0, "y": 0, "z": 3.0}}, (2, 1))
    assert p is not None and p["roll_deg"] == pytest.approx(10, abs=1e-6)
    assert p["pitch_deg"] == pytest.approx(0, abs=1e-6)


def test_slip_denominator_floor_avoids_blowup_at_low_speed(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "AXIS_PRIOR_PATH", tmp_path / "a.json")
    live = P.LiveMetrics()
    live.axis = (2, 1)
    for i in range(80):
        live.update(_wheel_sample(i, 3.0, 0.44), t=i * 0.1)
    # a 1,2 m/s las ruedas van 0,6 m/s de más: antes 50 %, ahora 0,6 / 2,0 = 30 %
    omega = (1.2 + 0.6) / 0.44
    out = live.update(_sample(_rot(0), 1.2, 0, vehicle_id="s_x", w_omega=[omega] * 4, t=9.0), t=9.0)
    assert out["slip_mean"] == pytest.approx(0.3, abs=0.01)
    assert out["slip_over_max_ms"] == pytest.approx(0.6, abs=0.02)
