"""Comprime las sesiones terminadas de data/sessions a .ndjson.gz (≈ 10× menos espacio).

Uso:
    python scripts/compact_sessions.py [--sessions data/sessions] [--older-than-min 15] [--dry-run]

Se omiten los ficheros modificados hace menos de `--older-than-min` minutos (pueden estar abiertos
por el grabador). Cada fichero se verifica leyendo el .gz antes de borrar el original. El análisis
(`report_profiles.py`, `analyze_session.py`) lee .ndjson y .ndjson.gz indistintamente.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from snowrunner_telemetry_api.console import use_utf8_output
from snowrunner_telemetry_api.analysis import compress_session

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    use_utf8_output()  # consolas cp1252 de Windows
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sessions", type=Path, default=ROOT / "data" / "sessions")
    ap.add_argument("--older-than-min", type=float, default=15.0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    limit = time.time() - args.older_than_min * 60
    before = after = 0
    done = 0
    for path in sorted(args.sessions.glob("*.ndjson")):
        if path.stat().st_mtime > limit:
            print(f"omitido (reciente): {path.name}")
            continue
        size = path.stat().st_size
        if args.dry_run:
            print(f"comprimiría: {path.name} ({size / 1e6:.2f} MB)")
            continue
        target = compress_session(path)
        before, after, done = before + size, after + target.stat().st_size, done + 1
        print(f"{path.name}: {size / 1e6:.2f} MB -> {target.stat().st_size / 1e6:.2f} MB")
    if done:
        print(f"{done} ficheros: {before / 1e6:.1f} MB -> {after / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
