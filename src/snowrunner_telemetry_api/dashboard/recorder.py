"""Grabación NDJSON de muestras del dashboard para analizar y calibrar el mod."""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from ..context import ContextTags

DEFAULT_DIR = Path(__file__).resolve().parents[3] / "data" / "sessions"

# Campos que usan los análisis y el dashboard. El resto (legado de entrada física, XInput,
# fuentes de depuración…) no aporta nada y supone ~60 % del tamaño de cada fila.
SLIM_FIELDS = (
    "sample_seq", "ts_ms", "vehicle_id", "probe_ok", "speed_kmh", "throttle_game", "brake_game", "steer_game",
    "fuel_pct", "fuel_liters", "fuel_liters_raw", "fuel_cap_liters", "fuel_source",
    "terrain_kind", "mud_grade", "mud_grade_label", "wheel_count", "wheel_grip",
    "surface_avg", "contact_avg", "surface_deform_avg", "grip_min", "grip_max",
    "contact_min", "contact_max", "vel", "pos", "rot", "ang_vel", "w_omega", "w_speed",
)


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", text).strip("_") or "sesion"


class SessionRecorder:
    """Escribe una línea JSON por muestra nueva, con `t` en segundos desde el inicio."""

    def __init__(
        self,
        label: str,
        directory: Path | None = None,
        meta: dict[str, Any] | None = None,
        context: ContextTags | None = None,
        fields: tuple[str, ...] | None = None,
    ) -> None:
        self._context = context
        self._fields = fields  # None = fila completa
        folder = directory or DEFAULT_DIR
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.path = folder / f"{_slug(label)}_{stamp}.ndjson"
        self._file = self.path.open("w", encoding="utf-8")
        if meta:
            self._file.write(json.dumps({"_meta": meta}, ensure_ascii=False) + "\n")
        self._started = time.monotonic()
        self._last_seq: object = None
        self.count = 0

    def write(self, sample: dict[str, Any]) -> bool:
        """Devuelve False si la muestra repite el `sample_seq` anterior."""
        seq = sample.get("sample_seq")
        if seq is not None and seq == self._last_seq:
            return False
        self._last_seq = seq
        row: dict[str, Any] = {"t": round(time.monotonic() - self._started, 3)}
        if self._fields is None:
            row.update(sample)
        else:
            row.update({k: sample[k] for k in self._fields if k in sample})
        ctx = self._context.current() if self._context is not None else {}
        if ctx:
            row["ctx"] = ctx
        self._file.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
        self._file.flush()
        self.count += 1
        return True

    def close(self) -> None:
        self._file.close()
