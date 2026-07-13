"""Configuración Fase 1 — modo CSV."""

from __future__ import annotations

import os
from pathlib import Path

API_VERSION = "0.1.0"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

DOCUMENTS_CSV = (
    Path.home()
    / "Documents"
    / "My Games"
    / "SnowRunner"
    / "base"
    / "telemetria_ce_log.csv"
)


def csv_path() -> Path:
    raw = os.environ.get("SNOWRUNNER_CSV_PATH", "").strip()
    if raw:
        return Path(raw).expanduser()
    return DOCUMENTS_CSV


def api_port() -> int:
    raw = os.environ.get("SNOWRUNNER_API_PORT", "").strip()
    if raw:
        return int(raw)
    return DEFAULT_PORT
