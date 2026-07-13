"""Lectura del CSV Havok (última fila)."""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .csv_header import CSV_COLUMNS


def _configure_csv_field_limit() -> None:
    target = max(csv.field_size_limit(), 4 * 1024 * 1024)
    try:
        csv.field_size_limit(target)
    except OverflowError:
        csv.field_size_limit(2**20)


_configure_csv_field_limit()


@dataclass(frozen=True)
class CsvSourceState:
    exists: bool
    readable: bool
    row_count: int
    last_mtime: datetime | None
    last_row: dict[str, str] | None
    error: str | None = None

    @property
    def filename(self) -> str:
        return "telemetria_ce_log.csv"


def read_last_row(path: Path) -> CsvSourceState:
    if not path.is_file():
        return CsvSourceState(
            exists=False,
            readable=False,
            row_count=0,
            last_mtime=None,
            last_row=None,
            error="csv_not_found",
        )

    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError as exc:
        return CsvSourceState(
            exists=True,
            readable=False,
            row_count=0,
            last_mtime=None,
            last_row=None,
            error=str(exc),
        )

    last_row: dict[str, str] | None = None
    row_count = 0
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames:
                # Normalizar nombres de columna (espacios accidentales).
                reader.fieldnames = [c.strip() for c in reader.fieldnames if c]
            for row in reader:
                cleaned = {k.strip(): (v or "").strip() for k, v in row.items() if k}
                if not any(cleaned.values()):
                    continue
                row_count += 1
                last_row = cleaned
    except OSError as exc:
        return CsvSourceState(
            exists=True,
            readable=False,
            row_count=0,
            last_mtime=mtime,
            last_row=None,
            error=str(exc),
        )
    except csv.Error as exc:
        return CsvSourceState(
            exists=True,
            readable=False,
            row_count=row_count,
            last_mtime=mtime,
            last_row=last_row,
            error=str(exc),
        )

    return CsvSourceState(
        exists=True,
        readable=True,
        row_count=row_count,
        last_mtime=mtime,
        last_row=last_row,
        error=None if last_row else "csv_empty",
    )


def expected_columns() -> tuple[str, ...]:
    return CSV_COLUMNS
