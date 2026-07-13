"""Mapeo vehicle_id CE → mod id (subset de camiones/registry.py del principal)."""

VEHICLE_MOD_ID: dict[str, str] = {
    "s_chevrolet_ck1500": "ck1500",
    "s_krs_58_bandit": "bandit",
    "s_fleetstar_f2070a": "fleetstar",
    "international_fleetstar_f2070a": "fleetstar",
    "s_khan_39_marshall": "marshall",
    "khan_39_marshall": "marshall",
    "s_tatra_t813": "t813",
    "tatra_t813": "t813",
    "s_gmc_9500": "mh9500",
    "s_gmc9500": "mh9500",
    "s_chevrolet_kodiakc70": "kodiak",
    "s_chevrolet_kodiakC70": "kodiak",
}


def vehicle_mod_id(ce_vehicle_id: str) -> str | None:
    key = (ce_vehicle_id or "").strip()
    if not key:
        return None
    return VEHICLE_MOD_ID.get(key)
