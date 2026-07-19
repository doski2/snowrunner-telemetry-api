"""python -m snowrunner_telemetry_api.dashboard"""

from __future__ import annotations

import argparse
import os
import sys

from .app import SpeedDashboard
from .metrics import CHART_METRICS, normalize_chart_metric
from .poll import api_base_url


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Dashboard SnowRunner — histórico de speed_kmh vía GET /v1/sample",
    )
    parser.add_argument(
        "--url",
        default=api_base_url(),
        help="Base URL de la API (default: SNOWRUNNER_API_URL o http://127.0.0.1:8765)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=int(os.environ.get("SNOWRUNNER_DASHBOARD_INTERVAL_MS", "500")),
        help="Intervalo de poll en ms (default: 500)",
    )
    parser.add_argument(
        "--history",
        type=int,
        default=int(os.environ.get("SNOWRUNNER_DASHBOARD_HISTORY", "300")),
        help="Puntos máximos en el gráfico (default: 300)",
    )
    parser.add_argument(
        "--source",
        choices=("auto", "api", "agent"),
        default=os.environ.get("SNOWRUNNER_DASHBOARD_SOURCE", "auto"),
        help="auto: API si hay CSV; si no, agente C# (default: auto)",
    )
    parser.add_argument(
        "--chart",
        choices=CHART_METRICS,
        default=os.environ.get("SNOWRUNNER_DASHBOARD_CHART", "speed_kmh"),
        help="Métrica del histórico: speed_kmh, fuel_pct o both (default: speed_kmh)",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Comparar terreno agente C# vs última fila CSV (API)",
    )
    args = parser.parse_args(argv)

    if args.interval < 100:
        print("[dashboard] intervalo mínimo 100 ms", file=sys.stderr)
        return 2
    if args.history < 10:
        print("[dashboard] history mínimo 10 puntos", file=sys.stderr)
        return 2

    SpeedDashboard(
        base_url=args.url.rstrip("/"),
        interval_ms=args.interval,
        history_len=args.history,
        source=args.source,
        chart_metric=normalize_chart_metric(args.chart),
        compare_csv=args.compare,
    ).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
