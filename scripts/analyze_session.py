"""Analiza una sesión grabada con `run_dashboard.bat --record`.

Uso:
    python scripts/analyze_session.py data/sessions/f1_..._.ndjson [--target objetivo.json]

`objetivo.json`: {"t_to_kmh": {"40": 12.0}, "vmax_kmh": 75}
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from snowrunner_telemetry_api.console import use_utf8_output
from snowrunner_telemetry_api.analysis import analyze, compare_targets, load_rows


def main() -> int:
    use_utf8_output()  # consolas cp1252 de Windows
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("session", type=Path)
    ap.add_argument("--target", type=Path, help="JSON con objetivos a comparar")
    args = ap.parse_args()

    rows = load_rows(args.session)
    if not rows:
        print("Sesión vacía.", file=sys.stderr)
        return 1
    result = analyze(rows)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.target:
        targets = json.loads(args.target.read_text(encoding="utf-8"))
        print("\nComparación con objetivo:")
        print("\n".join(compare_targets(result, targets)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
