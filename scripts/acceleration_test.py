"""Mide aceleración a fondo con el agente (memoria Havok) y guarda un JSON.

Con el camión parado, ejecuta el script y acelera a fondo en recta. Detecta el
arranque solo; termina cuando la velocidad se estabiliza o pasa --timeout.

Uso:
    python scripts/acceleration_test.py [--interval 100] [--timeout 90] [--label texto]

Salida: data/accel_<vehicle_id>_<fecha>.json con tiempos a 20/40/60/80 km/h y vmax.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECT = ROOT / "agent" / "SnowrunnerTelemetryAgent.csproj"
THRESHOLDS = (20, 40, 60, 80)
START_KMH = 1.0
PLATEAU_S = 6.0
PLATEAU_DELTA_KMH = 0.5


def stream_samples(interval_ms: int):
    cmd = [
        "dotnet", "run", "--project", str(PROJECT), "-v", "q", "--",
        "--loop", f"--interval={interval_ms}", "--memory-only",
    ]
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8"
    )
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.strip()
            if line.startswith("{"):
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    finally:
        proc.terminate()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--interval", type=int, default=100)
    ap.add_argument("--timeout", type=float, default=90.0)
    ap.add_argument("--label", default="")
    args = ap.parse_args()

    print("Esperando arranque (acelera a fondo en recta)...")
    t0: float | None = None
    start_wall = time.monotonic()
    times: dict[int, float] = {}
    vmax = 0.0
    last_gain_t = 0.0
    vehicle_id = ""
    trace: list[tuple[float, float]] = []

    for sample in stream_samples(args.interval):
        now = time.monotonic()
        speed = float(sample.get("speed_kmh", 0.0))
        vehicle_id = sample.get("vehicle_id") or vehicle_id

        if t0 is None:
            if speed >= START_KMH:
                t0 = now
                last_gain_t = 0.0
                print(f"Arranque detectado ({vehicle_id}).")
            elif now - start_wall > args.timeout:
                print("Timeout sin arranque.")
                return 3
            continue

        t = now - t0
        trace.append((round(t, 2), round(speed, 2)))
        if speed > vmax + PLATEAU_DELTA_KMH:
            vmax = speed
            last_gain_t = t
        else:
            vmax = max(vmax, speed)
        for th in THRESHOLDS:
            if th not in times and speed >= th:
                times[th] = round(t, 2)
                print(f"  0-{th} km/h: {t:.2f} s")
        if t - last_gain_t >= PLATEAU_S or t > args.timeout:
            break

    if t0 is None or not trace:
        print("Sin datos.")
        return 3

    result = {
        "vehicle_id": vehicle_id,
        "label": args.label,
        "date": datetime.now().isoformat(timespec="seconds"),
        "interval_ms": args.interval,
        "t_to_kmh": {str(k): v for k, v in times.items()},
        "vmax_kmh": round(vmax, 1),
        "trace": trace,
    }
    out = ROOT / "data" / f"accel_{vehicle_id}_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"vmax {vmax:.1f} km/h -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
