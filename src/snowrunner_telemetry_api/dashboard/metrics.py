"""Métricas disponibles en el dashboard."""

from __future__ import annotations

CHART_METRICS = ("speed_kmh", "fuel_pct", "both")

CHART_METRIC_LABELS: dict[str, str] = {
    "speed_kmh": "Velocidad",
    "fuel_pct": "Combustible",
    "both": "Ambos",
}

LABEL_TO_METRIC = {label: key for key, label in CHART_METRIC_LABELS.items()}


def normalize_chart_metric(value: str) -> str:
    if value in CHART_METRICS:
        return value
    return LABEL_TO_METRIC.get(value, "speed_kmh")
