"""Etiquetas de contexto (carga, neumáticos, diferencial…) que acompañan a cada fila grabada.

Viven en `data/context.json` y se leen en cada muestra (con caché por fecha del fichero), así que
se pueden cambiar mientras se juega con `python scripts/set_context.py carga=vacio` sin reiniciar
ni el grabador ni el dashboard.
"""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "context.json"
NO_CONTEXT = "sin etiqueta"


class ContextTags:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DEFAULT_PATH
        self._mtime: float | None = None
        self._data: dict[str, str] = {}

    def current(self) -> dict[str, str]:
        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            self._data, self._mtime = {}, None
            return {}
        if mtime != self._mtime:
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                self._data = {str(k): str(v) for k, v in raw.items()} if isinstance(raw, dict) else {}
            except (OSError, json.JSONDecodeError):
                self._data = {}
            self._mtime = mtime
        return dict(self._data)

    def _write(self, data: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        self._mtime = None  # fuerza la relectura

    def update(self, pairs: dict[str, str]) -> dict[str, str]:
        data = self.current()
        data.update(pairs)
        self._write(data)
        return data

    def unset(self, keys: list[str]) -> dict[str, str]:
        data = {k: v for k, v in self.current().items() if k not in keys}
        self._write(data)
        return data

    def clear(self) -> None:
        self._write({})


def parse_pairs(items: list[str]) -> dict[str, str]:
    """['carga=vacio', 'neumaticos=Ultima AT I'] -> dict. Lanza ValueError si falta el '='."""
    out: dict[str, str] = {}
    for item in items:
        key, sep, value = item.partition("=")
        if not sep or not key.strip():
            raise ValueError(f"se esperaba clave=valor, no {item!r}")
        out[key.strip()] = value.strip()
    return out


def signature(ctx: dict[str, str] | None) -> str:
    """Texto estable para agrupar: 'carga=vacio, neumaticos=Ultima AT I'."""
    if not ctx:
        return NO_CONTEXT
    return ", ".join(f"{k}={v}" for k, v in sorted(ctx.items()))
