"""Magnitudes derivadas de la telemetría: pendiente, aceleración neta, fuerza lateral, consumo.

Todo son funciones puras sobre filas/muestras del agente (`rot`, `vel`, `ang_vel`, `pos`, ...).
Convenciones: eje Y vertical (hacia arriba), `rot` = 3 columnas de la matriz de rotación del
cuerpo rígido (9 floats), unidades del juego en m/s y m.
"""

from __future__ import annotations

import json
import math
from collections import deque
from pathlib import Path
from typing import Any

G = 9.80665
MIN_MOVING_KMH = 3.0
MIN_SAMPLES_FOR_AXIS = 25
FUEL_WINDOW_S = 20.0
MIN_SLIP_SPEED_MS = 1.0  # por debajo, v/ω es ruido: no se calcula patinaje
MIN_OMEGA = 0.3
SLIP_DENOM_FLOOR_MS = 2.0  # a baja velocidad (ω·R − v) / v se dispara por ruido: se divide por al menos esto
MIN_RADIUS_SAMPLES = 60
MAX_GAP_S = 2.0
AXIS_PRIOR_PATH = Path(__file__).resolve().parents[2] / "data" / "forward_axis.json"

Vec = tuple[float, float, float]


def columns(rot: list[float] | None) -> list[Vec] | None:
    if not rot or len(rot) != 9:
        return None
    return [(rot[0], rot[1], rot[2]), (rot[3], rot[4], rot[5]), (rot[6], rot[7], rot[8])]


def velocity(sample: dict[str, Any]) -> Vec | None:
    v = sample.get("vel")
    if not isinstance(v, dict):
        return None
    try:
        return (float(v["x"]), float(v["y"]), float(v["z"]))
    except (TypeError, KeyError, ValueError):
        return None


def _dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Vec, b: Vec) -> Vec:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def detect_forward_axis(samples: list[dict[str, Any]]) -> tuple[int, int] | None:
    """(índice de columna, signo) del eje delantero: el más alineado con la velocidad al avanzar."""
    score = [0.0, 0.0, 0.0]
    n = 0
    for s in samples:
        cols, v = columns(s.get("rot")), velocity(s)
        if cols is None or v is None:
            continue
        speed = math.sqrt(_dot(v, v))
        if speed * 3.6 < MIN_MOVING_KMH:
            continue
        n += 1
        for k in range(3):
            score[k] += _dot(cols[k], v) / speed
    if n < MIN_SAMPLES_FOR_AXIS:
        return None
    best = max(range(3), key=lambda k: abs(score[k]))
    if abs(score[best]) / n < 0.5:  # ningún eje claramente alineado: datos ambiguos
        return None
    return best, 1 if score[best] > 0 else -1


def pose(sample: dict[str, Any], axis: tuple[int, int]) -> dict[str, float] | None:
    """Cabeceo, alabeo y pendiente (%) del vehículo. Cabeceo + = morro arriba; alabeo + = derecha arriba."""
    cols = columns(sample.get("rot"))
    if cols is None:
        return None
    k, sign = axis
    fwd = (sign * cols[k][0], sign * cols[k][1], sign * cols[k][2])
    up_idx = max((i for i in range(3) if i != k), key=lambda i: cols[i][1])
    up = cols[up_idx]
    if up[1] < 0:
        up = (-up[0], -up[1], -up[2])
    right = _cross(fwd, up)  # en un sistema dextrógiro con Y arriba, adelante × arriba = derecha
    pitch = math.asin(max(-1.0, min(1.0, fwd[1])))
    roll = math.asin(max(-1.0, min(1.0, right[1])))
    return {
        "pitch_deg": math.degrees(pitch),
        "roll_deg": math.degrees(roll),
        "slope_pct": math.tan(pitch) * 100.0,
        "v_long_ms": _dot(velocity(sample) or (0.0, 0.0, 0.0), fwd),
    }


def lateral_g(v_long_ms: float, yaw_rate: float) -> float:
    """Aceleración lateral aproximada (en g) = velocidad longitudinal × velocidad de guiñada."""
    return v_long_ms * yaw_rate / G


def net_drive_accel(a_long_ms2: float, pitch_deg: float) -> float:
    """Aceleración atribuible al motor: suma la componente de la gravedad a lo largo del vehículo."""
    return a_long_ms2 + G * math.sin(math.radians(pitch_deg))


def load_axis_prior() -> tuple[int, int] | None:
    try:
        data = json.loads(AXIS_PRIOR_PATH.read_text(encoding="utf-8"))
        return int(data["column"]), int(data["sign"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def save_axis_prior(axis: tuple[int, int]) -> None:
    try:
        AXIS_PRIOR_PATH.parent.mkdir(parents=True, exist_ok=True)
        AXIS_PRIOR_PATH.write_text(
            json.dumps({"column": axis[0], "sign": axis[1]}), encoding="utf-8"
        )
    except OSError:
        pass


class LiveMetrics:
    """Estado incremental para el dashboard: una llamada a `update` por muestra nueva."""

    def __init__(self) -> None:
        self.vehicle = ""
        self.axis: tuple[int, int] | None = load_axis_prior()
        self._buffer: list[dict[str, Any]] = []
        self._verified = False  # el eje se verifica con datos de cada camión; el guardado es solo un a priori
        self._hist: deque[tuple[float, float, float | None]] = deque(maxlen=200)
        self._last_pos: Vec | None = None
        self.distance_m = 0.0
        self._radii: deque[float] = deque(maxlen=800)

    def reset_vehicle(self, vehicle: str) -> None:
        self.vehicle = vehicle
        self._buffer.clear()
        self._verified = False
        self._hist.clear()
        self._last_pos = None
        self.distance_m = 0.0
        self._radii.clear()

    def update(self, sample: dict[str, Any], t: float) -> dict[str, Any]:
        vehicle = str(sample.get("vehicle_id") or "")
        if vehicle != self.vehicle:
            self.reset_vehicle(vehicle)

        out: dict[str, Any] = {"axis_ready": self.axis is not None}
        if not self._verified:
            self._buffer.append(sample)
            if len(self._buffer) >= MIN_SAMPLES_FOR_AXIS:
                found = detect_forward_axis(self._buffer)
                if found is not None:
                    self.axis = found
                    self._verified = True
                    self._buffer.clear()
                    save_axis_prior(found)
                elif len(self._buffer) > 600:  # sin movimiento claro: no acumular sin límite
                    del self._buffer[:300]
        if self.axis is not None:
            out["axis_ready"] = True
            p = pose(sample, self.axis)
            if p is not None:
                out.update(p)
                self._track_accel(out, sample, t)

        out.update(self._wheel_slip(sample, out.get("v_long_ms")))
        pos = sample.get("pos")
        if isinstance(pos, list) and len(pos) == 3:
            cur = (float(pos[0]), float(pos[1]), float(pos[2]))
            if self._last_pos is not None:
                step = math.dist(cur, self._last_pos)
                if step < 50:  # descarta teletransportes (carga de mapa, recuperación)
                    self.distance_m += step
            self._last_pos = cur
        out["distance_m"] = self.distance_m
        out.update(self._fuel_rates(sample, t))
        return out

    def _wheel_slip(self, sample: dict[str, Any], v_long: float | None) -> dict[str, float]:
        """Patinaje estimado por rueda: (ω·R − v) / max(v, 2 m/s). R (radio efectivo) se calibra con el camión."""
        omega = sample.get("w_omega")
        if v_long is None or not isinstance(omega, list) or not omega or v_long < MIN_SLIP_SPEED_MS:
            return {}
        try:
            omegas = [float(w) for w in omega]
        except (TypeError, ValueError):
            return {}
        self._radii.extend(v_long / w for w in omegas if w > MIN_OMEGA)
        if len(self._radii) < MIN_RADIUS_SAMPLES:
            return {}
        radius = sorted(self._radii)[len(self._radii) // 2]
        over = [w * radius - v_long for w in omegas]  # exceso de giro de cada rueda, m/s
        denom = max(v_long, SLIP_DENOM_FLOOR_MS)
        slips = [o / denom for o in over]
        return {
            "wheel_radius_m": radius,
            "slip_mean": sum(slips) / len(slips),
            "slip_max": max(slips),
            "slip_over_max_ms": max(over),
        }

    def _track_accel(self, out: dict[str, Any], sample: dict[str, Any], t: float) -> None:
        v_long = out["v_long_ms"]
        # lectura directa de memoria si existe; `fuel_liters` está interpolado por un modelo del agente
        fuel = _float(sample.get("fuel_liters_raw"))
        self._hist.append((t, v_long, fuel if fuel is not None else _float(sample.get("fuel_liters"))))
        window = [h for h in self._hist if t - h[0] <= 0.5]
        if len(window) >= 2 and window[-1][0] - window[0][0] >= 0.2:
            a = (window[-1][1] - window[0][1]) / (window[-1][0] - window[0][0])
            out["a_long_ms2"] = a
            out["a_net_ms2"] = net_drive_accel(a, out["pitch_deg"])
        ang = sample.get("ang_vel")
        if isinstance(ang, list) and len(ang) == 3:
            out["lat_g"] = lateral_g(v_long, float(ang[1]))

    def _fuel_rates(self, sample: dict[str, Any], t: float) -> dict[str, float]:
        pts = [(h[0], h[2]) for h in self._hist if h[2] is not None and t - h[0] <= FUEL_WINDOW_S]
        if len(pts) < 2 or pts[-1][0] - pts[0][0] < 3.0:
            return {}
        used = pts[0][1] - pts[-1][1]
        if used < 0:  # repostaje
            return {}
        lph = used / (pts[-1][0] - pts[0][0]) * 3600.0
        out = {"fuel_l_per_h": lph}
        speed = _float(sample.get("speed_kmh")) or 0.0
        if speed >= 5.0:
            out["fuel_l_per_100km"] = lph / speed * 100.0
        return out


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
