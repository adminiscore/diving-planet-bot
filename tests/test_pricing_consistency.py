"""
Cross-check that prices in services.json match pricing.json for every overlapping service.

Catches silent price drift when one file is updated without updating the other.
Run with: pytest tests/test_pricing_consistency.py -v
"""
import json
from pathlib import Path

import pytest

PRICING_PATH = Path("data/knowledge_base/pricing.json")
SERVICES_PATH = Path("data/knowledge_base/services.json")

# Maps (services.json service_id) → (pricing.json dotted path)
# Format: "origin.category.key"
SERVICE_PRICING_MAP = {
    # --- From Cartagena: dive services ---
    "2_dives_1_day":  "from_cartagena.servicios_buceo_snorkel.buzo_certificado_doble",
    "minicourse":     "from_cartagena.servicios_buceo_snorkel.minicurso_refresh",
    "snorkeling":     "from_cartagena.servicios_buceo_snorkel.snorkel_doble",
    # --- From Cartagena: packages ---
    "3_dives_1_day":  "from_cartagena.paquetes.paquete_3_buceos",
    "4_dives_2_days": "from_cartagena.paquetes.paquete_4_buceos_diurnos",
    "5_dives_2_days": "from_cartagena.paquetes.paquete_5_buceos",
    "7_dives_3_days": "from_cartagena.paquetes.paquete_7_buceos",
    "9_dives_4_days": "from_cartagena.paquetes.paquete_9_buceos",
    # --- From Cartagena: PADI courses ---
    "open_water":     "from_cartagena.cursos_buceo.curso_open_water",
    "advanced":       "from_cartagena.cursos_buceo.curso_avanzado",
    "rescue":         "from_cartagena.cursos_buceo.curso_rescate_efr",
    "referral":       "from_cartagena.cursos_buceo.curso_referido",
    # --- From Cartagena: specialties (price by dive count) ---
    "naturalist_specialty":         "from_cartagena.cursos_especialidades.especialidad_2_buceos",
    "fish_identification_specialty": "from_cartagena.cursos_especialidades.especialidad_2_buceos",
    "buoyancy_specialty":           "from_cartagena.cursos_especialidades.especialidad_2_buceos",
    "nitrox_specialty":             "from_cartagena.cursos_especialidades.especialidad_2_buceos",
    "mindful_diving":               "from_cartagena.cursos_especialidades.especialidad_4_buceos",
    # --- Already on island: dive services ---
    "1_dive_1_day_already_on_island":   "from_islands.servicios_buceo_snorkel.buzo_certificado_sencillo",
    "2_dives_1_day_already_on_island":  "from_islands.servicios_buceo_snorkel.buzo_certificado_doble",
    "minicourse_already_on_island":     "from_islands.servicios_buceo_snorkel.minicurso_refresh",
    "snorkeling_already_on_island":     "from_islands.servicios_buceo_snorkel.snorkel_doble",
    # --- Already on island: packages ---
    "3_dives_1_day_already_on_island":       "from_islands.paquetes.paquete_3_buceos",
    "4_dives_2_days_already_on_island":      "from_islands.paquetes.paquete_4_buceos_diurnos",
    "4_dives_2_days_mixed_already_on_island": "from_islands.paquetes.paquete_4_buceos_mixto",
    "5_dives_2_days_already_on_island":      "from_islands.paquetes.paquete_5_buceos",
    "7_dives_3_days_already_on_island":      "from_islands.paquetes.paquete_7_buceos",
    "9_dives_4_days_already_on_island":      "from_islands.paquetes.paquete_9_buceos",
    # --- Already on island: PADI courses ---
    "open_water_already_on_island": "from_islands.cursos_buceo.curso_open_water",
    "advanced_already_on_island":   "from_islands.cursos_buceo.curso_avanzado",
    "referral_already_on_island":   "from_islands.cursos_buceo.curso_referido",
    # --- Already on island: specialties ---
    "fish_identification_specialty_already_on_island": "from_islands.cursos_especialidades.especialidad_2_buceos",
    "nitrox_specialty_already_on_island":              "from_islands.cursos_especialidades.especialidad_2_buceos",
    "naturalist_specialty_already_on_island":          "from_islands.cursos_especialidades.especialidad_2_buceos",
    "buoyancy_specialty_already_on_island":            "from_islands.cursos_especialidades.especialidad_2_buceos",
}

# services.json field → pricing.json field
PRICE_FIELD_MAP = {
    "price_usd":        "usd_online",
    "price_usd_normal": "usd_normal",
    "price_cop":        "cop_online",
    "price_cop_normal": "cop_normal",
}


def _load():
    with PRICING_PATH.open(encoding="utf-8-sig") as f:
        pricing = json.load(f)
    with SERVICES_PATH.open(encoding="utf-8-sig") as f:
        services = json.load(f)["services"]
    return pricing, services


def _resolve(pricing: dict, dotted_path: str) -> dict:
    node = pricing
    for key in dotted_path.split("."):
        node = node[key]
    return node


@pytest.fixture(scope="module")
def data():
    return _load()


def _cases():
    try:
        pricing, services = _load()
    except Exception:
        return []

    cases = []
    for svc_id, pricing_path in SERVICE_PRICING_MAP.items():
        if svc_id not in services:
            continue
        try:
            p = _resolve(pricing, pricing_path)
        except KeyError:
            continue
        s = services[svc_id]
        for svc_field, pricing_field in PRICE_FIELD_MAP.items():
            sv = s.get(svc_field)
            pv = p.get(pricing_field)
            if sv is None or pv is None:
                continue
            cases.append((svc_id, svc_field, float(sv), float(pv), pricing_path))
    return cases


@pytest.mark.parametrize(
    "svc_id,field,svc_price,pricing_price,pricing_path",
    _cases(),
    ids=[f"{c[0]}.{c[1]}" for c in _cases()],
)
def test_price_matches(svc_id, field, svc_price, pricing_price, pricing_path):
    """Price in services.json must equal the corresponding field in pricing.json."""
    assert abs(svc_price - pricing_price) < 0.01, (
        f"{svc_id}.{field}: services.json={svc_price} "
        f"vs pricing.json ({pricing_path}.{PRICE_FIELD_MAP[field]})={pricing_price}"
    )


def test_all_mapped_services_exist_in_services_json():
    """Every service_id in SERVICE_PRICING_MAP must exist in services.json."""
    pricing, services = _load()
    missing = [sid for sid in SERVICE_PRICING_MAP if sid not in services]
    assert not missing, f"service IDs in map but missing from services.json: {missing}"


def test_all_pricing_paths_exist_in_pricing_json():
    """Every dotted path in SERVICE_PRICING_MAP must resolve in pricing.json."""
    pricing, _ = _load()
    bad_paths = []
    for svc_id, path in SERVICE_PRICING_MAP.items():
        try:
            _resolve(pricing, path)
        except KeyError as e:
            bad_paths.append(f"{svc_id} → {path} (key {e} not found)")
    assert not bad_paths, "Broken pricing paths:\n" + "\n".join(bad_paths)
