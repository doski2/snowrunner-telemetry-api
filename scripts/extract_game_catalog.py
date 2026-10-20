"""Extrae datos estáticos de SnowRunner (initial.pak, solo lectura) a un JSON.

Uso:
    python scripts/extract_game_catalog.py [--pak RUTA] [--out data/game_catalog.json]

Salida: capacidad de combustible por camión y coeficientes de fricción por tipo
de neumático. Sirve para validar `fuel_liters` y calibrar el clasificador de
terreno sin depender de offsets de memoria.
"""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path

DEFAULT_PAK = Path(
    r"C:\Program Files (x86)\Steam\steamapps\common\SnowRunner"
    r"\preload\paks\client\initial.pak"
)
TRUCK_RE = re.compile(r"^\[media\]/(?:_dlc/(?P<dlc>[^/]+)/)?classes/trucks/(?P<id>[^/]+)\.xml$")
FUEL_RE = re.compile(r'FuelCapacity="([\d.]+)"')
TIRE_RE = re.compile(r'DefaultTire="([^"]+)"')
WHEELS_RE = re.compile(r"<Wheel\s+_template=")
FRICTION_BLOCK_RE = re.compile(r"<WheelFriction>(.*?)</WheelFriction>", re.S)
FRICTION_ITEM_RE = re.compile(r"<(\w+)\s+([^>]*?)/>", re.S)
ATTR_RE = re.compile(r'(\w+)="([^"]*)"')


def read_text(zf: zipfile.ZipFile, name: str) -> str:
    return zf.read(name).decode("utf-8", "replace")


def extract_trucks(zf: zipfile.ZipFile) -> dict[str, dict]:
    trucks: dict[str, dict] = {}
    for name in zf.namelist():
        m = TRUCK_RE.match(name)
        if not m:
            continue
        text = read_text(zf, name)
        fuel = FUEL_RE.search(text)
        if not fuel:
            continue  # tuning/addon sin TruckData base
        tire = TIRE_RE.search(text)
        trucks[m["id"]] = {
            "fuel_capacity_l": float(fuel[1]),
            "default_tire": tire[1] if tire else None,
            "wheel_count": len(WHEELS_RE.findall(text)),
            "dlc": m["dlc"],
        }
    return trucks


def extract_tire_friction(zf: zipfile.ZipFile) -> dict[str, dict]:
    text = read_text(zf, "[media]/_templates/trucks.xml")
    block = FRICTION_BLOCK_RE.search(text)
    if not block:
        return {}
    out: dict[str, dict] = {}
    for tag, attrs in FRICTION_ITEM_RE.findall(block[1]):
        out[tag] = {
            k: (float(v) if re.fullmatch(r"-?[\d.]+", v) else v)
            for k, v in ATTR_RE.findall(attrs)
            if k != "UiName"
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pak", type=Path, default=DEFAULT_PAK)
    ap.add_argument("--out", type=Path, default=Path("data/game_catalog.json"))
    args = ap.parse_args()

    with zipfile.ZipFile(args.pak) as zf:
        catalog = {
            "source": args.pak.name,
            "trucks": extract_trucks(zf),
            "tire_friction": extract_tire_friction(zf),
        }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{len(catalog['trucks'])} camiones, {len(catalog['tire_friction'])} tipos de neumático -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
