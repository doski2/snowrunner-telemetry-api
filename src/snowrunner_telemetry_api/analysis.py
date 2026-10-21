"""Métricas de una sesión grabada (NDJSON) para calibrar el mod frente a datos reales."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from . import physics

SPEED_THRESHOLDS_KMH = (20, 40, 60, 80)
START_KMH = 1.0
IDLE_KMH = 0.5


def load_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "_meta" not in row:
            rows.append(row)
    # `ts_ms` (reloj del agente) es más exacto que la hora de lectura en Python
    stamped = [r for r in rows if isinstance(r.get("ts_ms"), (int, float))]
    if stamped and len(stamped) == len(rows):
        base = stamped[0]["ts_ms"]
        for r in rows:
            r["t"] = round((r["ts_ms"] - base) / 1000.0, 3)
    return rows


def enrich(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Añade magnitudes derivadas (pendiente, aceleración neta, fuerza lateral, consumo, distancia).

    Necesita `rot`/`vel` en las filas (agente con orientación); si no hay, devuelve las filas tal cual.
    """
    if not rows or not any(r.get("rot") for r in rows) or any("t" not in r for r in rows):
        return rows
    axis = physics.detect_forward_axis(rows) or physics.load_axis_prior()
    if axis is None:
        return rows
    live = physics.LiveMetrics()
    live.axis = axis
    out = []
    for row in rows:
        extra = live.update(row, float(row["t"]))
        out.append(
            {**row, **{k: round(v, 4) for k, v in extra.items() if isinstance(v, (int, float)) and k != "axis_ready"}}
        )
    return out


def load_meta(path: Path) -> dict[str, Any]:
    """Cabecera `_meta` de una sesión (vacía si no existe)."""
    with path.open(encoding="utf-8") as fh:
        first = fh.readline().strip()
    try:
        return json.loads(first).get("_meta", {}) if first else {}
    except json.JSONDecodeError:
        return {}


def _num(row: dict[str, Any], key: str) -> float | None:
    try:
        return float(row[key])
    except (KeyError, TypeError, ValueError):
        return None


def acceleration(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Tiempos hasta cada umbral desde el primer instante con velocidad >= START_KMH."""
    start_t: float | None = None
    times: dict[str, float] = {}
    vmax = 0.0
    for row in rows:
        speed, t = _num(row, "speed_kmh"), _num(row, "t")
        if speed is None or t is None:
            continue
        vmax = max(vmax, speed)
        if start_t is None:
            if speed >= START_KMH:
                start_t = t
            continue
        for th in SPEED_THRESHOLDS_KMH:
            if str(th) not in times and speed >= th:
                times[str(th)] = round(t - start_t, 2)
    return {"t_to_kmh": times, "vmax_kmh": round(vmax, 1)}


MAX_GAP_S = 5.0


def fuel(rows: list[dict[str, Any]], kind: str | None = None) -> dict[str, Any]:
    """Consumo (L/h) en reposo y en movimiento; ignora subidas (repostaje) y huecos largos.

    Con `kind` solo cuenta los tramos cuyo terreno de partida es ese.
    """
    used = {"idle": 0.0, "moving": 0.0}
    secs = {"idle": 0.0, "moving": 0.0}
    prev: tuple[float, float, float, str] | None = None
    for row in rows:
        t, liters, speed = _num(row, "t"), _num(row, "fuel_liters"), _num(row, "speed_kmh")
        if t is None or liters is None or speed is None:
            continue
        here = str(row.get("terrain_kind") or "sin_dato")
        if prev is not None and t - prev[0] <= MAX_GAP_S and (kind is None or prev[3] == kind):
            dt, delta = t - prev[0], prev[1] - liters
            state = "idle" if prev[2] < IDLE_KMH else "moving"
            secs[state] += dt
            if delta > 0:
                used[state] += delta
        prev = (t, liters, speed, here)
    return {
        state: {
            "seconds": round(secs[state], 1),
            "liters": round(used[state], 3),
            "l_per_h": round(used[state] / secs[state] * 3600, 2) if secs[state] > 5 else None,
        }
        for state in used
    }


def terrain(rows: list[dict[str, Any]]) -> dict[str, Any]:
    kinds = Counter(str(r.get("terrain_kind") or "") for r in rows)
    total = sum(kinds.values()) or 1
    mud_speeds = [
        s for r in rows if r.get("terrain_kind") == "mud" and (s := _num(r, "speed_kmh")) is not None
    ]
    return {
        "share": {k or "sin_dato": round(v / total, 3) for k, v in kinds.most_common()},
        "mud_speed_mean_kmh": round(sum(mud_speeds) / len(mud_speeds), 2) if mud_speeds else None,
        "mud_speed_max_kmh": round(max(mud_speeds), 2) if mud_speeds else None,
    }


SPEED_BANDS_KMH = ((0, 5), (5, 15), (15, 30), (30, 60), (60, 1000))
THROTTLE_BINS = ((0.05, 0.25), (0.25, 0.5), (0.5, 0.75), (0.75, 1.01))
MIN_BIN_SAMPLES = 5
IDEAL_FRACTION = 0.9


def band_label(speed: float) -> str:
    for lo, hi in SPEED_BANDS_KMH:
        if lo <= speed < hi:
            return f"{lo}-{hi if hi < 1000 else 'max'}"
    return ""


def accel_points(rows: list[dict[str, Any]]) -> list[tuple[str, str, float, float]]:
    """(terreno, banda, gas, aceleración km/h/s) con derivada centrada de 2 pasos."""
    points = []
    for k in range(len(rows) - 2):
        a, b = rows[k], rows[k + 2]
        t0, t1 = _num(a, "t"), _num(b, "t")
        v0, v1 = _num(a, "speed_kmh"), _num(b, "speed_kmh")
        gas = _num(rows[k + 1], "throttle_game")
        mid = _num(rows[k + 1], "speed_kmh")
        if None in (t0, t1, v0, v1, gas, mid) or not 0.1 <= t1 - t0 <= 1.0:
            continue
        kind = str(rows[k + 1].get("terrain_kind") or "sin_dato")
        a_net = _num(rows[k + 1], "a_net_ms2")  # corregida por pendiente (km/h/s = m/s² × 3,6)
        accel = a_net * 3.6 if a_net is not None else (v1 - v0) / (t1 - t0)
        points.append((kind, band_label(mid), gas, accel))
    return points


def ideal_throttle(sessions: list[list[dict[str, Any]]]) -> dict[str, Any]:
    """Gas mínimo que logra IDEAL_FRACTION de la mejor aceleración, por terreno y velocidad."""
    groups: dict[tuple[str, str], dict[int, list[float]]] = {}
    for rows in sessions:
        for kind, band, gas, accel in accel_points(enrich(rows)):
            for i, (lo, hi) in enumerate(THROTTLE_BINS):
                if lo <= gas < hi:
                    groups.setdefault((kind, band), {}).setdefault(i, []).append(accel)
    table: dict[str, Any] = {}
    for (kind, band), bins in sorted(groups.items()):
        means = {i: sum(v) / len(v) for i, v in bins.items() if len(v) >= MIN_BIN_SAMPLES}
        if not means:
            continue
        best = max(means.values())
        entry: dict[str, Any] = {
            "samples": sum(len(v) for v in bins.values()),
            "mean_accel_by_throttle": {
                f"{THROTTLE_BINS[i][0]:.2f}-{min(THROTTLE_BINS[i][1], 1.0):.2f}": round(m, 2)
                for i, m in sorted(means.items())
            },
        }
        if best <= 0:
            entry["ideal_throttle"] = None
            entry["note"] = "sin ganancia de velocidad con ningún gas"
        else:
            ideal = min(i for i, m in means.items() if m >= IDEAL_FRACTION * best)
            lo, hi = THROTTLE_BINS[ideal]
            entry["ideal_throttle"] = [lo, min(hi, 1.0)]
            entry["best_accel"] = round(best, 2)
        table[f"{kind}|{band}"] = entry
    return table


def _percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def profile_report(sessions: list[list[dict[str, Any]]]) -> dict[str, Any]:
    """Perfil de un camión por terreno: tiempo, velocidad, uso del gas y consumo.

    Usa percentiles (no medias) porque el juego normal mezcla pendiente, marcha y carga.
    """
    by_kind: dict[str, list[dict[str, Any]]] = {}
    sessions = [enrich(rows) for rows in sessions]
    for rows in sessions:
        for prev, row in zip(rows, rows[1:]):
            t0, t1 = _num(prev, "t"), _num(row, "t")
            if t0 is None or t1 is None or not 0 < t1 - t0 <= MAX_GAP_S:
                continue
            kind = str(prev.get("terrain_kind") or "sin_dato")
            by_kind.setdefault(kind, []).append(
                {
                    "dt": t1 - t0,
                    "speed": _num(prev, "speed_kmh"),
                    "gas": _num(prev, "throttle_game"),
                    "slope": _num(prev, "slope_pct"),
                    "lat": _num(prev, "lat_g"),
                }
            )

    report: dict[str, Any] = {}
    for kind, items in sorted(by_kind.items(), key=lambda kv: -sum(i["dt"] for i in kv[1])):
        seconds = sum(i["dt"] for i in items)
        moving = [i for i in items if i["speed"] is not None and i["speed"] >= START_KMH]
        speeds = [i["speed"] for i in moving]
        gases = [i["gas"] for i in moving if i["gas"] is not None]
        fuel_stats = {}
        for rows in sessions:
            part = fuel(rows, kind)["moving"]
            for key in ("seconds", "liters"):
                fuel_stats[key] = fuel_stats.get(key, 0.0) + part[key]
        report[kind] = {
            "minutes": round(seconds / 60, 1),
            "moving_share": round(sum(i["dt"] for i in moving) / seconds, 2) if seconds else 0.0,
            "speed_p50_kmh": round(_percentile(speeds, 0.5), 1) if speeds else None,
            "speed_p90_kmh": round(_percentile(speeds, 0.9), 1) if speeds else None,
            "slope_abs_p90_pct": (
                round(_percentile([abs(i["slope"]) for i in moving if i["slope"] is not None], 0.9), 1)
                if any(i["slope"] is not None for i in moving)
                else None
            ),
            "lat_g_abs_p90": (
                round(_percentile([abs(i["lat"]) for i in moving if i["lat"] is not None], 0.9), 2)
                if any(i["lat"] is not None for i in moving)
                else None
            ),
            "gas_p50": round(_percentile(gases, 0.5), 2) if gases else None,
            "gas_full_share": round(sum(g >= 0.95 for g in gases) / len(gases), 2) if gases else None,
            "fuel_l_per_h_moving": (
                round(fuel_stats["liters"] / fuel_stats["seconds"] * 3600, 1)
                if fuel_stats.get("seconds", 0) > 60
                else None
            ),
        }
    return report


def analyze(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ids = Counter(str(r.get("vehicle_id") or "") for r in rows if r.get("vehicle_id"))
    duration = (_num(rows[-1], "t") or 0.0) if rows else 0.0
    return {
        "vehicle_id": ids.most_common(1)[0][0] if ids else "",
        "samples": len(rows),
        "duration_s": round(duration, 1),
        "acceleration": acceleration(rows),
        "fuel": fuel(rows),
        "terrain": terrain(rows),
        "ideal_throttle": ideal_throttle([rows]),
    }


def compare_targets(result: dict[str, Any], targets: dict[str, Any]) -> list[str]:
    """Diferencias medido − objetivo para `t_to_kmh` y `vmax_kmh`."""
    lines: list[str] = []
    accel = result["acceleration"]
    for th, target in (targets.get("t_to_kmh") or {}).items():
        got = accel["t_to_kmh"].get(str(th))
        lines.append(
            f"0-{th} km/h: objetivo {target} s, medido "
            + (f"{got} s ({got - float(target):+.2f})" if got is not None else "no alcanzado")
        )
    if "vmax_kmh" in targets:
        lines.append(
            f"vmax: objetivo {targets['vmax_kmh']} km/h, medido {accel['vmax_kmh']} "
            f"({accel['vmax_kmh'] - float(targets['vmax_kmh']):+.1f})"
        )
    return lines
