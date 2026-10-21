"""python -m snowrunner_telemetry_api.dashboard"""

from __future__ import annotations

import argparse
import os
import sys

from .app import SpeedDashboard
from .poll import api_base_url


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Dashboard SnowRunner — panel en vivo (agente C# o API)",
    )
    parser.add_argument(
        "--url",
        default=api_base_url(),
        help="Base URL de la API (default: SNOWRUNNER_API_URL o http://127.0.0.1:8765)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=int(os.environ.get("SNOWRUNNER_DASHBOARD_INTERVAL_MS", "150")),
        help="Cada cuántos ms repinta la ventana (default: 150; el agente muestrea a 100 ms)",
    )
    parser.add_argument(
        "--source",
        choices=("auto", "api", "agent"),
        default=os.environ.get("SNOWRUNNER_DASHBOARD_SOURCE", "auto"),
        help="auto: API si hay CSV; si no, agente C# (default: auto)",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Comparar terreno agente C# vs última fila CSV (API)",
    )
    parser.add_argument(
        "--record",
        metavar="ETIQUETA",
        default="dash",
        help="Prefijo de los ficheros de data/sessions (default: dash). Se graba siempre, a 100 ms, un fichero por camión",
    )
    parser.add_argument("--no-record", action="store_true", help="No grabar")
    parser.add_argument("--full-rows", action="store_true", help="Grabar todos los campos del agente (3× más grande)")
    parser.add_argument(
        "--cap-seconds",
        type=float,
        default=0.0,
        help="Situación ya cubierta con N s: guardar solo 1 de cada 5 filas (default: 0 = nunca aligerar)",
    )
    args = parser.parse_args(argv)

    if args.interval < 100:
        print("[dashboard] intervalo mínimo 100 ms", file=sys.stderr)
        return 2

    SpeedDashboard(
        base_url=args.url.rstrip("/"),
        interval_ms=args.interval,
        source=args.source,
        compare_csv=args.compare,
        record_label=None if args.no_record else args.record,
        full_rows=args.full_rows,
        cap_seconds=args.cap_seconds,
    ).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
