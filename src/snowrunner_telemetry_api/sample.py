"""CSV row → ce_sample_v1."""

from __future__ import annotations

from typing import Any

from .csv_header import FLOAT_FIELDS, INT_FIELDS

SCHEMA_VERSION = "ce_sample_v1"

# CSV antiguo: throttle=-1 con velocidad alta (no fiable como input).
LEGACY_THROTTLE_SENTINEL = -1.0


def _parse_float(raw: str) -> float | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_int(raw: str) -> int | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _apply_throttle_fields(sample: dict[str, Any], row: dict[str, str]) -> None:
    """Normaliza gas: preferir throttle_input; legacy throttle si falta input.

    Reglas (alineado con importar_ce_csv / CONTRATO-DATOS):
    - Si hay throttle_input en CSV → usarlo.
    - Si no hay throttle_input pero throttle es válido (≠ -1) → throttle_input = throttle.
    - throttle legacy = throttle_input si existe, si no throttle_motor, si no throttle crudo.
    """
    thr_in = _parse_float(row.get("throttle_input", ""))
    thr_mot = _parse_float(row.get("throttle_motor", ""))
    thr_legacy = _parse_float(row.get("throttle", ""))

    if thr_in is None and thr_legacy is not None and thr_legacy != LEGACY_THROTTLE_SENTINEL:
        thr_in = thr_legacy
        sample["throttle_input_legacy_fallback"] = True

    if thr_in is not None:
        sample["throttle_input"] = thr_in
    if thr_mot is not None:
        sample["throttle_motor"] = thr_mot

    if thr_in is not None:
        sample["throttle"] = thr_in
    elif thr_mot is not None:
        sample["throttle"] = thr_mot
    elif thr_legacy is not None:
        sample["throttle"] = thr_legacy


def csv_row_to_sample(row: dict[str, str]) -> dict[str, Any]:
    sample: dict[str, Any] = {"schema_version": SCHEMA_VERSION}

    for key, value in row.items():
        if key in ("throttle_input", "throttle_motor", "throttle"):
            continue
        if key in FLOAT_FIELDS:
            parsed = _parse_float(value)
            if parsed is not None:
                sample[key] = parsed
        elif key in INT_FIELDS:
            parsed = _parse_int(value)
            if parsed is not None:
                sample[key] = parsed
        else:
            text = (value or "").strip()
            if text:
                sample[key] = text

    _apply_throttle_fields(sample, row)
    return sample


def required_fields_present(sample: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for key in ("t_s", "speed_kmh", "vehicle_id", "terrain_kind", "chain"):
        if sample.get(key) in (None, ""):
            missing.append(key)
    return missing
