"""Métricas de una sesión grabada (NDJSON) para calibrar el mod frente a datos reales."""

from __future__ import annotations

import gzip
import json
from collections import Counter
from pathlib import Path
from typing import Any

from . import physics
from .context import signature

SPEED_THRESHOLDS_KMH = (20, 40, 60, 80)
START_KMH = 1.0
IDLE_KMH = 0.5


def open_session(path: Path):
    """Abre una sesión como texto, sea `.ndjson` o `.ndjson.gz`."""
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open(encoding="utf-8")


def session_files(folder: Path) -> list[Path]:
    return sorted([*folder.glob("*.ndjson"), *folder.glob("*.ndjson.gz")])


def compress_session(path: Path) -> Path:
    """Comprime `x.ndjson` a `x.ndjson.gz`; solo borra el original si el resultado se lee igual."""
    target = path.with_name(path.name + ".gz")
    before = path.read_bytes()
    with gzip.open(target, "wb", compresslevel=6) as out:
        out.write(before)
    with gzip.open(target, "rb") as check:
        if check.read() != before:
            target.unlink(missing_ok=True)
            raise OSError(f"la compresión de {path.name} no coincide con el original")
    path.unlink()
    return target


def load_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with open_session(path) as fh:
        lines = fh.read().splitlines()
    for line in lines:
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
    with open_session(path) as fh:
        first = fh.readline().strip()
    try:
        return json.loads(first).get("_meta", {}) if first else {}
    except json.JSONDecodeError:
        return {}


def fuel_value(row: dict[str, Any]) -> tuple[float | None, bool]:
    """(litros, es_lectura_directa). `fuel_liters` lo interpola un modelo del agente entre lecturas
    reales (no depende del gas real), así que solo `fuel_liters_raw` vale para medir consumo."""
    raw = _num(row, "fuel_liters_raw")
    if raw is not None:
        return raw, True
    return _num(row, "fuel_liters"), False


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
        t, (liters, _), speed = _num(row, "t"), fuel_value(row), _num(row, "speed_kmh")
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
    points: list[tuple[str, str, float, float]] = []
    for k in range(len(rows) - 2):
        a, b = rows[k], rows[k + 2]
        t0, t1 = _num(a, "t"), _num(b, "t")
        v0, v1 = _num(a, "speed_kmh"), _num(b, "speed_kmh")
        gas = _num(rows[k + 1], "throttle_game")
        mid = _num(rows[k + 1], "speed_kmh")
        if t0 is None or t1 is None or v0 is None or v1 is None or gas is None or mid is None:
            continue
        if not 0.1 <= t1 - t0 <= 1.0:
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


# --- Eficiencia: L/100 km y avance por tramo de gas, terreno y contexto -------------------------

EFFICIENCY_BINS = ((0.05, 0.25), (0.25, 0.5), (0.5, 0.75), (0.75, 0.95), (0.95, 1.01))
MIN_BIN_SECONDS = 10.0
MIN_BIN_DISTANCE_M = 30.0
HIGH_SLIP = 0.3  # patinaje medio > 30 % = tracción perdida
MAX_JUMP_M = 50.0  # saltos mayores (carga de mapa, recuperación) no cuentan como distancia


def efficiency_bin_label(index: int) -> str:
    lo, hi = EFFICIENCY_BINS[index]
    return f"{lo:.2f}-{min(hi, 1.0):.2f}"


def _step_distance(prev: dict[str, Any], row: dict[str, Any], dt: float) -> float:
    a, b = prev.get("pos"), row.get("pos")
    if isinstance(a, list) and isinstance(b, list) and len(a) == 3 and len(b) == 3:
        step = sum((float(x) - float(y)) ** 2 for x, y in zip(a, b)) ** 0.5
        if step <= MAX_JUMP_M:
            return step
    speed = _num(prev, "speed_kmh") or 0.0
    return speed / 3.6 * dt


def efficiency_report(sessions: list[list[dict[str, Any]]]) -> dict[str, Any]:
    """Por «terreno | contexto»: consumo por distancia y avance en cada tramo de gas.

    El gas más eficiente es el de menor L/100 km entre los tramos con datos suficientes. Incluye
    cobertura (qué tramos faltan) y una confianza orientativa.
    """
    acc: dict[tuple[str, str], dict[int, dict[str, float]]] = {}
    for rows in sessions:
        enriched = enrich(rows)
        for prev, row in zip(enriched, enriched[1:]):
            t0, t1 = _num(prev, "t"), _num(row, "t")
            gas = _num(prev, "throttle_game")
            (f0, direct0), (f1, direct1) = fuel_value(prev), fuel_value(row)
            if t0 is None or t1 is None or gas is None or f0 is None or f1 is None:
                continue
            dt = t1 - t0
            if not 0 < dt <= MAX_GAP_S or f1 > f0 + 1e-6:  # hueco largo o repostaje
                continue
            idx = next((i for i, (lo, hi) in enumerate(EFFICIENCY_BINS) if lo <= gas < hi), None)
            if idx is None:
                continue
            key = (str(prev.get("terrain_kind") or "sin_dato"), signature(prev.get("ctx")))
            b = acc.setdefault(key, {}).setdefault(
                idx,
                {
                    "seconds": 0.0, "distance": 0.0, "liters": 0.0, "speed_s": 0.0, "a_s": 0.0,
                    "a_dt": 0.0, "slip_s": 0.0, "slip_dt": 0.0, "slip_hi_dt": 0.0, "direct_dt": 0.0,
                },
            )
            b["seconds"] += dt
            b["direct_dt"] += dt if direct0 and direct1 else 0.0
            b["distance"] += _step_distance(prev, row, dt)
            b["liters"] += f0 - f1
            b["speed_s"] += (_num(prev, "speed_kmh") or 0.0) * dt
            a_net = _num(prev, "a_net_ms2")
            if a_net is not None:
                b["a_s"] += a_net * dt
                b["a_dt"] += dt
            slip = _num(prev, "slip_mean")
            if slip is not None:
                b["slip_s"] += slip * dt
                b["slip_dt"] += dt
                if slip > HIGH_SLIP:
                    b["slip_hi_dt"] += dt

    report: dict[str, Any] = {}
    for (kind, ctx), bins in sorted(acc.items()):
        entry_bins: dict[str, Any] = {}
        valid: dict[int, float] = {}
        for i in range(len(EFFICIENCY_BINS)):
            b = bins.get(i)
            if b is None:
                continue
            l100 = b["liters"] * 100000.0 / b["distance"] if b["distance"] > 1.0 else None
            enough = b["seconds"] >= MIN_BIN_SECONDS and b["distance"] >= MIN_BIN_DISTANCE_M and b["liters"] > 0
            if enough and l100 is not None:
                valid[i] = l100
            entry_bins[efficiency_bin_label(i)] = {
                "seconds": round(b["seconds"], 1),
                "distance_m": round(b["distance"], 1),
                "liters": round(b["liters"], 3),
                "l_per_100km": round(l100, 1) if l100 is not None else None,
                "mean_speed_kmh": round(b["speed_s"] / b["seconds"], 1),
                "mean_a_net_ms2": round(b["a_s"] / b["a_dt"], 2) if b["a_dt"] else None,
                "mean_slip": round(b["slip_s"] / b["slip_dt"], 3) if b["slip_dt"] else None,
                "high_slip_share": round(b["slip_hi_dt"] / b["slip_dt"], 2) if b["slip_dt"] else None,
                "enough_data": enough,
            }
        direct_share = sum(b["direct_dt"] for b in bins.values()) / max(1e-9, sum(b["seconds"] for b in bins.values()))
        entry: dict[str, Any] = {
            # «memoria» = lectura directa; «modelo» = interpolado por el agente (no fiable para eficiencia)
            "fuel_basis": "memoria" if direct_share > 0.9 else "modelo",
            "bins": entry_bins,
            # cobertura por tiempo: qué tramos de gas conviene seguir grabando
            "missing_bins": [
                efficiency_bin_label(i)
                for i in range(len(EFFICIENCY_BINS))
                if bins.get(i, {}).get("seconds", 0.0) < MIN_BIN_SECONDS
            ],
            "most_efficient": None,
        }
        if valid:
            best = min(valid, key=lambda i: valid[i])
            lo, hi = EFFICIENCY_BINS[best]
            entry["most_efficient"] = [lo, min(hi, 1.0)]
            entry["best_l_per_100km"] = round(valid[best], 1)
            top = len(EFFICIENCY_BINS) - 1
            if top in valid and top != best:
                entry["full_throttle_extra_pct"] = round((valid[top] / valid[best] - 1) * 100, 0)
            seconds_best = bins[best]["seconds"]
            entry["confidence"] = (
                "alta" if len(valid) >= 3 and seconds_best >= 60 else "media" if len(valid) >= 2 else "baja"
            )
        else:
            entry["confidence"] = "sin datos suficientes"
        report[f"{kind}|{ctx}"] = entry
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
