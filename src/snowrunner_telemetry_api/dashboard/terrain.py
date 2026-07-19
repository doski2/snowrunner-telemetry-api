"""Terreno — formato y comparación agente vs API CSV."""

from __future__ import annotations

from typing import Any


def parse_optional_int(sample: dict[str, Any], key: str) -> int | None:
    raw = sample.get(key)
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def format_terrain_summary(sample: dict[str, Any]) -> str:
    kind = str(sample.get("terrain_kind") or "").strip()
    label = str(sample.get("mud_grade_label") or "").strip()
    grip = sample.get("wheel_grip")
    contact = sample.get("contact_avg")

    if not kind and label:
        kind = label
    if not kind:
        return "—"

    parts = [kind]
    if label and label != kind:
        parts.append(label)
    if grip is not None and grip != "":
        try:
            parts.append(f"grip {float(grip):.2f}")
        except (TypeError, ValueError):
            pass
    if contact is not None and contact != "":
        try:
            parts.append(f"contact {float(contact):.2f}")
        except (TypeError, ValueError):
            pass
    return " · ".join(parts)


def _float_close(a: float | None, b: float | None, *, tol: float) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= tol


def compare_terrain(agent: dict[str, Any], api: dict[str, Any]) -> str:
    """Resumen corto agente vs CSV para la barra de estado."""
    agent_kind = str(agent.get("terrain_kind") or "").strip()
    api_kind = str(api.get("terrain_kind") or "").strip()
    agent_label = str(agent.get("mud_grade_label") or "").strip()
    api_label = str(api.get("mud_grade_label") or "").strip()

    if not agent_kind and not api_kind:
        return "Comparar: sin terrain_kind en agente ni CSV"

    kind_match = agent_kind == api_kind if agent_kind and api_kind else False
    label_match = agent_label == api_label if agent_label and api_label else kind_match

    agent_grip = _to_float(agent.get("wheel_grip"))
    api_grip = _to_float(api.get("wheel_grip"))
    grip_match = _float_close(agent_grip, api_grip, tol=0.08)

    agent_contact = _to_float(agent.get("contact_avg"))
    api_contact = _to_float(api.get("contact_avg"))
    contact_match = _float_close(agent_contact, api_contact, tol=0.06)

    verdict = "OK" if kind_match and label_match and grip_match and contact_match else "REVISAR"
    agent_txt = format_terrain_summary(agent)
    api_txt = format_terrain_summary(api)
    return f"Comparar [{verdict}] agente: {agent_txt} | CSV: {api_txt}"


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
