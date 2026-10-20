"""Clasificación terreno por rueda — paridad con agent/Havok/WheelTerrainReader.cs y memoria_havok.py."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SURFACE_POSITIVE_THRESHOLD = 0.25
SAT_GRIP_MIN = 0.95
SAT_CONTACT_MIN = 0.95
SAT_DEFORM_MAX = -0.5
SAT_BC_DEEP_MUD_THRESHOLD = -0.130
SAT_BC_FIRM_MAX = -0.050
SAT_BC_ASPHALT_MIN = -0.100
SAT_DEFORM_DEEP_MUD_THRESHOLD = -0.9975


@dataclass(frozen=True)
class WheelContact:
    grip: float
    contact: float
    deform: float
    bc: float = 0.0


def effective_surface(surface_b4: float, contact_ec: float) -> float:
    return surface_b4 if surface_b4 > SURFACE_POSITIVE_THRESHOLD else contact_ec


def classify_wheel_contact(
    grip: float,
    surface: float,
    *,
    deform: float | None = None,
) -> str:
    if grip < 0.06 and surface > 0.68:
        return "ice"
    if (
        deform is not None
        and deform > 0.55
        and grip < 0.45
        and surface > 0.55
    ):
        return "snow"
    if (grip > 0.45 and surface > 0.30) or (surface > 0.68 and grip > 0.12):
        return "hard"
    if grip < 0.25 or (surface < 0.62 and grip < 0.40):
        return "mud"
    return "soft"


def is_grip_contact_saturated(wheels: list[WheelContact]) -> bool:
    if not wheels:
        return False
    grips = [w.grip for w in wheels]
    contacts = [w.contact for w in wheels]
    deforms = [w.deform for w in wheels]
    return (
        min(grips) >= SAT_GRIP_MIN
        and min(contacts) >= SAT_CONTACT_MIN
        and max(deforms) < SAT_DEFORM_MAX
    )


def classify_saturated_kind(wheels: list[WheelContact]) -> str:
    """Bandit-like: +2FC/+2EC saturados; +2BC varía (negativo profundo, ~-0.09 o positivo)."""
    bc_values = [w.bc for w in wheels]
    if not bc_values:
        return "hard"

    bc_min = min(bc_values)
    deform_avg = sum(w.deform for w in wheels) / len(wheels)

    if bc_min > SAT_BC_FIRM_MAX:
        return "mud"
    if bc_min < SAT_BC_DEEP_MUD_THRESHOLD:
        return "mud"
    if bc_min >= SAT_BC_ASPHALT_MIN:
        return "hard"
    if deform_avg < SAT_DEFORM_DEEP_MUD_THRESHOLD:
        return "mud"
    return "hard"


def resolve_dominant_kind(kinds: list[str]) -> tuple[str, str, bool]:
    if not kinds:
        return "unknown", "", False
    counts: dict[str, int] = {}
    for kind in kinds:
        counts[kind] = counts.get(kind, 0) + 1
    if len(counts) == 1:
        only = kinds[0]
        return only, only, False
    top = max(counts, key=lambda k: counts[k])
    if counts[top] > len(kinds) / 2:
        return top, top, len(counts) > 1
    return "mixed", "mixed", True


def classify_terrain_from_wheels(wheels: list[WheelContact]) -> dict[str, Any]:
    if not wheels:
        return {
            "terrain_kind": "unknown",
            "surface_wheel": "",
            "wheel_grip": "",
            "wheel_kinds": "",
            "terrain_source": "wheel_model",
        }

    if is_grip_contact_saturated(wheels):
        kind = classify_saturated_kind(wheels)
        kinds = [kind] * len(wheels)
        grip_avg = sum(w.grip for w in wheels) / len(wheels)
        surf_avg = sum(effective_surface(w.deform, w.contact) for w in wheels) / len(wheels)
        return {
            "terrain_kind": kind,
            "surface_wheel": kind,
            "wheel_grip": f"{grip_avg:.3f}",
            "surface_avg": f"{surf_avg:.3f}",
            "wheel_kinds": "|".join(kinds),
            "terrain_source": "wheel_model;saturated_secondary",
        }

    kinds: list[str] = []
    grips: list[float] = []
    surfaces: list[float] = []
    for wheel in wheels:
        surface = effective_surface(wheel.deform, wheel.contact)
        kinds.append(
            classify_wheel_contact(wheel.grip, surface, deform=wheel.deform)
        )
        grips.append(wheel.grip)
        surfaces.append(surface)

    terrain_kind, surface_wheel, _ = resolve_dominant_kind(kinds)
    grip_avg = sum(grips) / len(grips)
    surf_avg = sum(surfaces) / len(surfaces) if surfaces else 0.0
    return {
        "terrain_kind": terrain_kind,
        "surface_wheel": surface_wheel,
        "wheel_grip": f"{grip_avg:.3f}",
        "surface_avg": f"{surf_avg:.3f}",
        "wheel_kinds": "|".join(kinds),
        "terrain_source": "wheel_model",
    }
