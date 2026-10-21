"""Informe por camión y terreno de las sesiones grabadas con `record_play.bat`.

Uso:
    python scripts/report_profiles.py [--sessions data/sessions] [--vehicle s_krs_58_bandit]
        [--write-ideal]        # escribe data/ideal_throttle.json (gas con más aceleración neta)
        [--efficiency]         # tabla de L/100 km por gas, terreno y etiquetas de contexto
        [--write-efficiency]   # escribe data/efficiency.json para el dashboard
        [--rebuild-coverage]   # recalcula data/coverage.json desde todas las sesiones
"""

from __future__ import annotations

import argparse
import sys
import json
from collections import defaultdict
from pathlib import Path

from snowrunner_telemetry_api.coverage import CoverageTracker
from snowrunner_telemetry_api.console import use_utf8_output
from snowrunner_telemetry_api.analysis import (
    efficiency_report,
    ideal_throttle,
    load_rows,
    profile_report,
    session_files,
)

ROOT = Path(__file__).resolve().parent.parent


def load_by_vehicle(folder: Path) -> dict[str, list[list[dict]]]:
    grouped: dict[str, list[list[dict]]] = defaultdict(list)
    for path in session_files(folder):
        rows = load_rows(path)
        ids = {str(r["vehicle_id"]) for r in rows if r.get("vehicle_id")}
        if len(ids) == 1:
            grouped[ids.pop()].append(rows)
    return grouped


def print_efficiency(report: dict) -> None:
    if not report:
        print("  (sin datos de combustible y avance)")
        return
    for key, entry in report.items():
        terrain, ctx = key.split("|", 1)
        best = entry["most_efficient"]
        head = f"  {terrain} · {ctx}"
        if best:
            head += f"  →  eficiente {best[0] * 100:.0f}–{best[1] * 100:.0f} % ({entry['best_l_per_100km']} L/100 km)"
            if "full_throttle_extra_pct" in entry:
                head += f", a fondo +{entry['full_throttle_extra_pct']:.0f} %"
        print(f"{head}   [confianza: {entry['confidence']}]")
        if entry.get("fuel_basis") == "modelo":
            print("    AVISO: combustible interpolado por el agente (sesión grabada sin `fuel_liters_raw`);"
                  " los L/100 km NO miden el consumo real del gas. Regraba para datos fiables.")
        print(f"    {'gas':<10}{'seg':>7}{'m':>8}{'L':>8}{'L/100km':>9}{'v med':>8}{'a neta':>8}{'patin %':>9}")
        for label, b in entry["bins"].items():
            mark = " ◄" if best and label == f"{best[0]:.2f}-{best[1]:.2f}" else ""
            l100 = "—" if b["l_per_100km"] is None else b["l_per_100km"]
            a = "—" if b["mean_a_net_ms2"] is None else b["mean_a_net_ms2"]
            slip = "—" if b.get("mean_slip") is None else f"{b['mean_slip'] * 100:.0f}"
            weak = "" if b["enough_data"] else "  (pocos datos)"
            print(f"    {label:<10}{b['seconds']:>7}{b['distance_m']:>8}{b['liters']:>8}{l100:>9}{b['mean_speed_kmh']:>8}{a:>8}{slip:>9}{mark}{weak}")
        if entry["missing_bins"]:
            print(f"    faltan por grabar (< 10 s): {', '.join(entry['missing_bins'])}")


def main() -> int:
    use_utf8_output()  # consolas cp1252 de Windows
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sessions", type=Path, default=ROOT / "data" / "sessions")
    ap.add_argument("--vehicle")
    ap.add_argument("--write-ideal", action="store_true")
    ap.add_argument("--efficiency", action="store_true")
    ap.add_argument("--write-efficiency", action="store_true")
    ap.add_argument("--rebuild-coverage", action="store_true")
    args = ap.parse_args()

    grouped = load_by_vehicle(args.sessions)
    if args.vehicle:
        grouped = {k: v for k, v in grouped.items() if k == args.vehicle}
    if not grouped:
        print(f"Sin sesiones en {args.sessions}")
        return 1

    ideal: dict[str, dict] = {}
    efficiency: dict[str, dict] = {}
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
        if args.efficiency or args.write_efficiency:
            efficiency[vehicle] = efficiency_report(sessions)
            print("\n  -- eficiencia (L/100 km por tramo de gas) --")
            print_efficiency(efficiency[vehicle])

    if args.write_ideal:
        out = ROOT / "data" / "ideal_throttle.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(ideal, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nTabla de gas ideal -> {out}")
    if args.rebuild_coverage:
        tracker = CoverageTracker()
        tracker.reset()
        for sessions in grouped.values():
            for rows in sessions:
                tracker.add_rows(rows)
        tracker.save()
        print(f"Cobertura reconstruida -> {tracker.path}")
    if args.write_efficiency:
        out = ROOT / "data" / "efficiency.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(efficiency, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Tabla de eficiencia -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
