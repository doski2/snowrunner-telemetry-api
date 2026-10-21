"""Modelo de presentación del dashboard: de una muestra a los textos que se muestran."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .advice import IdealThrottleTable, format_advice
from .poll import parse_optional_float


@dataclass(frozen=True)
class LiveView:
    speed_text: str
    gas_pct: float | None
    gas_text: str
    gas_advice: str
    fuel_pct: float | None
    fuel_text: str
    terrain_title: str
    terrain_detail: str
    vehicle: str
    source: str
    tilt_text: str = "—"
    tilt_detail: str = ""
    accel_text: str = "—"
    accel_detail: str = ""
    consumption_text: str = "—"
    consumption_detail: str = ""


def _fuel_text(pct: float | None, liters: float | None, capacity: float | None) -> str:
    if pct is None:
        return "—"
    text = f"{pct:.0f} %"
    if liters is not None:
        text += f"  ·  {liters:.0f} / {capacity:.0f} L" if capacity else f"  ·  {liters:.0f} L"
    return text


def _terrain(sample: dict[str, Any]) -> tuple[str, str]:
    kind = str(sample.get("terrain_kind") or "").strip()
    if not kind:
        return "—", "sin terrain_kind (¿juego abierto?)"
    title = kind.upper()
    mud_label = str(sample.get("mud_grade_label") or "").strip()
    if mud_label and mud_label != kind:
        title = f"{title} ({mud_label.replace('_', ' ')})"
    parts: list[str] = []
    grip = parse_optional_float(sample, "wheel_grip")
    surface = parse_optional_float(sample, "surface_avg")
    contact = parse_optional_float(sample, "contact_avg")
    if grip is not None:
        parts.append(f"grip {grip:.2f}")
    if surface is not None:
        parts.append(f"surface {surface:.2f}")
    elif contact is not None:
        parts.append(f"contact {contact:.2f}")
    if sample.get("wheel_count") not in (None, "", 0):
        parts.append(f"{sample['wheel_count']} ruedas")
    return title, " · ".join(parts)


def _dynamics(m: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    if "slope_pct" in m:
        out["tilt_text"] = f"{m['slope_pct']:+.0f} %"
        out["tilt_detail"] = f"cabeceo {m['pitch_deg']:+.1f}° · alabeo {m['roll_deg']:+.1f}°"
    elif not m.get("axis_ready", True):
        out["tilt_detail"] = "calibrando eje: avanza unos segundos"
    if "a_net_ms2" in m:
        out["accel_text"] = f"{m['a_net_ms2']:+.1f} m/s²"
        detail = f"medida {m.get('a_long_ms2', 0.0):+.1f}"
        if "lat_g" in m:
            detail += f" · lateral {abs(m['lat_g']):.2f} g"
        out["accel_detail"] = detail
    if "fuel_l_per_h" in m:
        out["consumption_text"] = f"{m['fuel_l_per_h']:.1f} L/h"
        parts = []
        if "fuel_l_per_100km" in m:
            parts.append(f"{m['fuel_l_per_100km']:.0f} L/100 km")
        parts.append(f"{m.get('distance_m', 0.0) / 1000:.2f} km")
        out["consumption_detail"] = " · ".join(parts)
    elif m.get("distance_m"):
        out["consumption_detail"] = f"{m['distance_m'] / 1000:.2f} km recorridos"
    return out


def build_view(
    sample: dict[str, Any],
    speed: float,
    table: IdealThrottleTable,
    metrics: dict[str, Any] | None = None,
) -> LiveView:
    gas = parse_optional_float(sample, "throttle_game")
    kind = str(sample.get("terrain_kind") or "").strip()
    vehicle = str(sample.get("vehicle_id") or "")
    if gas is None:
        gas_pct, gas_text, advice = None, "—", "sin lectura del acelerador del juego"
    else:
        gas_pct = gas * 100
        gas_text = f"{gas_pct:.0f} %"
        advice = format_advice(table.lookup(vehicle, kind, speed), gas)

    fuel = parse_optional_float(sample, "fuel_pct")
    title, detail = _terrain(sample)
    return LiveView(
        speed_text=f"{speed:.1f}",
        gas_pct=gas_pct,
        gas_text=gas_text,
        gas_advice=advice,
        fuel_pct=fuel,
        fuel_text=_fuel_text(
            fuel,
            parse_optional_float(sample, "fuel_liters"),
            parse_optional_float(sample, "fuel_cap_liters"),
        ),
        terrain_title=title,
        terrain_detail=detail,
        vehicle=vehicle or "—",
        source=str(sample.get("fuel_source") or sample.get("source") or sample.get("schema_version") or "—"),
        **_dynamics(metrics or {}),
    )
