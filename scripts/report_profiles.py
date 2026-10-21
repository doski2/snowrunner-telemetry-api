"""Informe por camión y terreno de las sesiones grabadas con `record_play.bat`.

Uso:
    python scripts/report_profiles.py [--sessions data/sessions] [--vehicle s_krs_58_bandit]
        [--write-ideal]   # además escribe data/ideal_throttle.json para el dashboard
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from snowrunner_telemetry_api.analysis import ideal_throttle, load_rows, profile_report

ROOT = Path(__file__).resolve().parent.parent


def load_by_vehicle(folder: Path) -> dict[str, list[list[dict]]]:
    grouped: dict[str, list[list[dict]]] = defaultdict(list)
    for path in sorted(folder.glob("*.ndjson")):
        rows = load_rows(path)
        ids = {str(r["vehicle_id"]) for r in rows if r.get("vehicle_id")}
        if len(ids) == 1:
            grouped[ids.pop()].append(rows)
    return grouped


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sessions", type=Path, default=ROOT / "data" / "sessions")
    ap.add_argument("--vehicle")
    ap.add_argument("--write-ideal", action="store_true")
    args = ap.parse_args()

    grouped = load_by_vehicle(args.sessions)
    if args.vehicle:
        grouped = {k: v for k, v in grouped.items() if k == args.vehicle}
    if not grouped:
        print(f"Sin sesiones en {args.sessions}")
        return 1

    ideal: dict[str, dict] = {}
    for vehicle, sessions in sorted(grouped.items()):
        total = sum(len(s) for s in sessions)
        print(f"\n=== {vehicle}  ({len(sessions)} sesiones, {total} filas) ===")
        header = f"{'terreno':<10}{'min':>7}{'mov%':>6}{'v p50':>7}{'v p90':>7}{'gas p50':>9}{'gas100%':>9}{'L/h':>7}"
        print(header)
        for kind, r in profile_report(sessions).items():
            def f(x, w, spec=""):
                return f"{'—' if x is None else format(x, spec):>{w}}"

            print(
                f"{kind:<10}{r['minutes']:>7}{r['moving_share'] * 100:>5.0f}%"
                f"{f(r['speed_p50_kmh'], 7)}{f(r['speed_p90_kmh'], 7)}"
                f"{f(r['gas_p50'], 9)}{f(r['gas_full_share'], 9)}{f(r['fuel_l_per_h_moving'], 7)}"
            )
        ideal[vehicle] = ideal_throttle(sessions)

    if args.write_ideal:
        out = ROOT / "data" / "ideal_throttle.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(ideal, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nTabla de gas ideal -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
