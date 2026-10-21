"""Cambia las etiquetas de contexto que se graban con cada muestra (data/context.json).

Uso:
    python scripts/set_context.py carga=vacio neumaticos="Ultima AT I" diff=on
    python scripts/set_context.py --show
    python scripts/set_context.py --unset diff
    python scripts/set_context.py --clear

Claves sugeridas: carga (vacio/bastidor/remolque), neumaticos, diff (on/off), reductora (on/off),
awd (on/off). Son texto libre: lo que escribas se usa tal cual para agrupar los informes.
Se aplican en caliente al grabador y al dashboard que estén abiertos.
"""

from __future__ import annotations

import argparse
import json
import sys

from snowrunner_telemetry_api.context import ContextTags, parse_pairs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pairs", nargs="*", help="clave=valor")
    ap.add_argument("--show", action="store_true", help="muestra las etiquetas actuales")
    ap.add_argument("--unset", nargs="+", metavar="CLAVE", help="quita etiquetas")
    ap.add_argument("--clear", action="store_true", help="quita todas")
    args = ap.parse_args()

    tags = ContextTags()
    try:
        if args.clear:
            tags.clear()
        if args.unset:
            tags.unset(args.unset)
        if args.pairs:
            tags.update(parse_pairs(args.pairs))
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    print(json.dumps(tags.current(), indent=2, ensure_ascii=False) if tags.current() else "(sin etiquetas)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
