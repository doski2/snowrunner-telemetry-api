"""Grabación NDJSON de muestras del dashboard para analizar y calibrar el mod."""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_DIR = Path(__file__).resolve().parents[3] / "data" / "sessions"


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", text).strip("_") or "sesion"


class SessionRecorder:
    """Escribe una línea JSON por muestra nueva, con `t` en segundos desde el inicio."""

    def __init__(
        self, label: str, directory: Path | None = None, meta: dict[str, Any] | None = None
    ) -> None:
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
        row = {"t": round(time.monotonic() - self._started, 3), "label": self.path.stem}
        row.update(sample)
        self._file.write(json.dumps(row, ensure_ascii=False) + "\n")
        self._file.flush()
        self.count += 1
        return True

    def close(self) -> None:
        self._file.close()
