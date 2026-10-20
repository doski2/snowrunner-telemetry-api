import json
from pathlib import Path

import pytest

from snowrunner_telemetry_api.terrain_classifier import (
    WheelContact,
    classify_terrain_from_wheels,
    is_grip_contact_saturated,
)

FIXTURES = Path(__file__).parent / "fixtures" / "wheel_snaps"

EXPECTED = {
    "asfalto_bandit": "hard",
    "barro_bandit": "mud",
    "asfalto_bandit_live": "hard",
    "barro_bandit_live": "mud",
    "barro_bandit_live_posbc": "mud",
    "asfalto": "mixed",  # GMC: ruedas discordantes con clasificador base
    "barro": "mud",
    "asfalto_fs": "hard",
    "garaje_bandit": "hard",
}


def _load_wheels(name: str) -> list[WheelContact]:
    data = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    wheels: list[WheelContact] = []
    for row in data["wheels"]:
        wheels.append(
            WheelContact(
                grip=float(row["grip"]),
                contact=float(row["contact"]),
                deform=float(row["deform"]),
                bc=float(row.get("bc") or 0.0),
            )
        )
    return wheels


@pytest.mark.parametrize("snap,expected", EXPECTED.items())
def test_wheel_snap_classification(snap: str, expected: str) -> None:
    wheels = _load_wheels(snap)
    result = classify_terrain_from_wheels(wheels)
    assert result["terrain_kind"] == expected, result


def test_bandit_snapshots_use_saturated_path() -> None:
    for snap in ("asfalto_bandit", "barro_bandit"):
        wheels = _load_wheels(snap)
        assert is_grip_contact_saturated(wheels)
        result = classify_terrain_from_wheels(wheels)
        assert "saturated_secondary" in result["terrain_source"]


def test_fleetstar_not_saturated() -> None:
    wheels = _load_wheels("asfalto_fs")
    assert not is_grip_contact_saturated(wheels)
