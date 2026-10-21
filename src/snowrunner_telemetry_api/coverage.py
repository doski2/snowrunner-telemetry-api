"""Cobertura de perfiles: cuántos segundos llevamos de cada situación y qué tramos de gas faltan.

Situación = camión × terreno × etiquetas de contexto × pendiente × tramo de gas. El acumulado se
guarda en `data/coverage.json` para que el dashboard sepa, al abrirse, lo que ya está grabado.
Sirve para dos cosas: decir qué falta por cubrir y, opcionalmente, aligerar lo que ya sobra.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import physics
from .analysis import EFFICIENCY_BINS, efficiency_bin_label
from .context import signature

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "coverage.json"
TARGET_SECONDS = 60.0
MIN_GAS = EFFICIENCY_BINS[0][0]
MAX_DT_S = 1.0
FLAT_SLOPE_PCT = 5.0
SAVE_EVERY_S = 60.0

BIN_LABELS = [efficiency_bin_label(i) for i in range(len(EFFICIENCY_BINS))]


def gas_bin(gas: float | None) -> str | None:
    if gas is None:
        return None
    for i, (lo, hi) in enumerate(EFFICIENCY_BINS):
        if lo <= gas < hi:
            return BIN_LABELS[i]
    return None


def human_bin(label: str) -> str:
    """'0.50-0.75' -> '50–75 %'; el último tramo se lee '≥95 %'."""
    lo, hi = label.split("-")
    if BIN_LABELS and label == BIN_LABELS[-1]:
        return f"≥{float(lo) * 100:.0f} %"
    return f"{float(lo) * 100:.0f}–{float(hi) * 100:.0f} %"


def slope_band(sample: dict[str, Any], axis: tuple[int, int] | None) -> str:
    if axis is None:
        return "n/d"
    pose = physics.pose(sample, axis)
    if pose is None:
        return "n/d"
    if pose["slope_pct"] >= FLAT_SLOPE_PCT:
        return "subida"
    if pose["slope_pct"] <= -FLAT_SLOPE_PCT:
        return "bajada"
    return "llano"


@dataclass(frozen=True)
class Coverage:
    percent: float
    seconds_by_bin: dict[str, float]
    missing: list[str]
    total_seconds: float


class CoverageTracker:
    def __init__(self, path: Path | None = None, target_s: float = TARGET_SECONDS) -> None:
        self.path = path or DEFAULT_PATH
        self.target_s = target_s
        self._lock = threading.Lock()
        # counters[vehiculo][terreno][etiquetas][pendiente][tramo] = segundos
        self._counters: dict[str, Any] = {}
        self._last: tuple[str, float] | None = None
        self._last_save = 0.0
        self._dirty = False
        self._axis = physics.load_axis_prior()
        self._load()

    # ------------------------------------------------------------------ persistencia

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data.get("counters"), dict):
                self._counters = data["counters"]
        except (OSError, ValueError, AttributeError):
            self._counters = {}

    def save(self) -> None:
        with self._lock:
            if not self._dirty:
                return
            payload = {"target_seconds": self.target_s, "counters": self._counters}
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                self._dirty = False
            except OSError:
                pass

    def maybe_save(self, now: float) -> None:
        if now - self._last_save >= SAVE_EVERY_S:
            self._last_save = now
            self.save()

    # ------------------------------------------------------------------ acumulación

    def situation(self, sample: dict[str, Any], ctx: dict[str, str] | None) -> tuple[str, str, str, str, str] | None:
        vehicle = str(sample.get("vehicle_id") or "")
        try:
            gas = float(sample["throttle_game"])
        except (KeyError, TypeError, ValueError):
            return None
        label = gas_bin(gas)
        if not vehicle or label is None:
            return None
        terrain = str(sample.get("terrain_kind") or "sin_dato")
        return vehicle, terrain, signature(ctx), slope_band(sample, self._axis), label

    def update(self, sample: dict[str, Any], ctx: dict[str, str] | None, now: float) -> None:
        """Suma el tiempo transcurrido desde la muestra anterior a la situación actual."""
        vehicle = str(sample.get("vehicle_id") or "")
        ts = sample.get("ts_ms")
        t = float(ts) / 1000.0 if isinstance(ts, (int, float)) else now
        prev, self._last = self._last, (vehicle, t)
        if prev is None or prev[0] != vehicle:
            return
        dt = t - prev[1]
        sit = self.situation(sample, ctx)
        if sit is None or not 0 < dt <= MAX_DT_S:
            return
        with self._lock:
            node = self._counters
            for part in sit[:-1]:
                node = node.setdefault(part, {})
            node[sit[-1]] = node.get(sit[-1], 0.0) + dt
            self._dirty = True

    def seconds(self, sit: tuple[str, str, str, str, str]) -> float:
        with self._lock:
            node: Any = self._counters
            for part in sit:
                node = node.get(part) if isinstance(node, dict) else None
                if node is None:
                    return 0.0
            return float(node)

    # ------------------------------------------------------------------ consulta

    def status(self, vehicle: str, terrain: str, ctx: dict[str, str] | None) -> Coverage:
        sig = signature(ctx)
        by_bin = dict.fromkeys(BIN_LABELS, 0.0)
        with self._lock:
            slopes = ((self._counters.get(vehicle) or {}).get(terrain) or {}).get(sig) or {}
            for bins in slopes.values():
                for label, seconds in bins.items():
                    if label in by_bin:
                        by_bin[label] += float(seconds)
        percent = 100.0 * sum(min(s / self.target_s, 1.0) for s in by_bin.values()) / len(BIN_LABELS)
        return Coverage(
            percent=percent,
            seconds_by_bin=by_bin,
            missing=[label for label, s in by_bin.items() if s < self.target_s],
            total_seconds=sum(by_bin.values()),
        )

    def hint(self, vehicle: str, terrain: str, ctx: dict[str, str] | None) -> str:
        cov = self.status(vehicle, terrain, ctx)
        text = f"{terrain} · {signature(ctx)}: {cov.percent:.0f} % completo"
        if cov.missing:
            text += " · falta gas " + ", ".join(human_bin(m) for m in cov.missing)
        return text

    def reset(self) -> None:
        with self._lock:
            self._counters = {}
            self._dirty = True
        self._last = None

    def add_rows(self, rows: list[dict[str, Any]]) -> None:
        """Reconstruye contadores desde filas ya grabadas (usa `ts_ms` o `t`, y `ctx` por fila)."""
        self._last = None
        for row in rows:
            t = row.get("t")
            self.update(row, row.get("ctx"), float(t) if isinstance(t, (int, float)) else 0.0)
