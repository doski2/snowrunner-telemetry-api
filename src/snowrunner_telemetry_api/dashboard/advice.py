"""Sugerencia de gas según terreno y velocidad, a partir de data/ideal_throttle.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..analysis import band_label
from ..context import signature

DEFAULT_PATH = Path(__file__).resolve().parents[3] / "data" / "ideal_throttle.json"
MARGIN = 0.1


class IdealThrottleTable:
    """Carga perezosa con recarga automática si el fichero cambia."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DEFAULT_PATH
        self._mtime: float | None = None
        self._data: dict[str, Any] = {}

    def _reload(self) -> None:
        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            self._data, self._mtime = {}, None
            return
        if mtime != self._mtime:
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                self._data = {}
            self._mtime = mtime

    def lookup(self, vehicle_id: str, terrain_kind: str, speed_kmh: float) -> dict[str, Any] | None:
        self._reload()
        key = f"{terrain_kind or 'sin_dato'}|{band_label(speed_kmh)}"
        return (self._data.get(vehicle_id) or {}).get(key)


def format_advice(entry: dict[str, Any] | None, gas: float | None) -> str:
    """Texto corto para el dashboard."""
    if entry is None:
        return "sin datos grabados para esta situación"
    ideal = entry.get("ideal_throttle")
    if ideal is None:
        return "ningún gas gana velocidad aquí"
    lo, hi = float(ideal[0]), float(ideal[1])
    text = f"ideal {lo * 100:.0f}–{hi * 100:.0f} %"
    if gas is None:
        return text
    if gas > hi + MARGIN:
        return f"{text} — sobra gas"
    if gas < lo - MARGIN:
        return f"{text} — puedes dar más"
    return f"{text} — correcto"


EFFICIENCY_PATH = DEFAULT_PATH.with_name("efficiency.json")


class EfficiencyTable(IdealThrottleTable):
    """Tabla de gas más eficiente (L/100 km) por camión, terreno y etiquetas de contexto."""

    def __init__(self, path: Path | None = None) -> None:
        super().__init__(path or EFFICIENCY_PATH)

    def lookup_ctx(
        self, vehicle_id: str, terrain_kind: str, ctx: dict[str, str] | None
    ) -> dict[str, Any] | None:
        self._reload()
        key = f"{terrain_kind or 'sin_dato'}|{signature(ctx)}"
        return (self._data.get(vehicle_id) or {}).get(key)


def format_efficiency(entry: dict[str, Any] | None) -> str:
    if not entry or not entry.get("most_efficient"):
        return ""
    lo, hi = entry["most_efficient"]
    text = f"eficiente {lo * 100:.0f}–{hi * 100:.0f} % (~{entry['best_l_per_100km']:.0f} L/100 km)"
    if entry.get("full_throttle_extra_pct"):
        text += f" · a fondo +{entry['full_throttle_extra_pct']:.0f} %"
    if entry.get("confidence") == "baja":
        text += " · datos escasos"
    return text
