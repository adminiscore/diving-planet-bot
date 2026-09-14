"""F3a del plan de dominio de actividades (docs/robustness/activity-domain-plan.md).

Las tablas de datos que el codigo mantenia a mano pasan a derivarse del registro
(`data/knowledge_base/activities.json`) o de `services.json`. Donde el resultado es
el mismo, estos tests lo fijan; donde cambia, es porque la tabla a mano estaba mal
(y el test dice por que).
"""

import json
from pathlib import Path

from src.agents import conversational_core as core
from src.agents import supervisor
from src.domain import activities as dom
from src.flows import catalog

_SERVICES_RAW = json.loads(
    (Path(__file__).resolve().parents[1] / "data" / "knowledge_base" / "services.json")
    .read_text(encoding="utf-8-sig")
)["services"]


def test_dead_tables_are_gone():
    assert not hasattr(core, "_PRODUCT_ACTIVITIES")
    assert not hasattr(supervisor, "_REMEMBER_ACTIVITY_MAP")
    assert not hasattr(catalog, "SERVICE_TO_CART_TYPE")


def test_cart_types_of_day_activities_come_from_the_registry():
    """Mismo resultado que la tabla a mano, ahora derivado."""
    assert core._ACTIVITY_TO_CART_TYPE == {
        "certified_diving": "cert", "minicourse": "beginner", "snorkel": "snorkel",
    }


def test_activity_to_service_id_comes_from_the_registry():
    legacy = {
        "certified_diving": "2_dives_1_day", "minicourse": "minicourse", "snorkel": "snorkeling",
        "padi_open_water": "open_water", "padi_advanced": "advanced", "padi_rescue": "rescue",
        "padi_divemaster": "divemaster",
    }
    for activity_id, service_id in legacy.items():
        assert supervisor._ACTIVITY_TO_SERVICE_ID[activity_id] == service_id
    assert "padi_course" not in supervisor._ACTIVITY_TO_SERVICE_ID  # sin nivel, sin servicio


def test_island_map_covers_every_island_variant_including_3_and_4_dives():
    """D5: la lista a mano no tenia las variantes de 3 y 4 inmersiones."""
    for service_id in _SERVICES_RAW:
        island = f"{service_id}_already_on_island"
        if island in _SERVICES_RAW:
            assert catalog.ISLAND_SERVICE_MAP[service_id] == island
    assert catalog.ISLAND_SERVICE_MAP["3_dives_1_day"] == "3_dives_1_day_already_on_island"
    assert catalog.ISLAND_SERVICE_MAP["4_dives_2_days"] == "4_dives_2_days_already_on_island"


def test_multi_day_services_include_two_day_courses():
    """Los cursos de 2 dias obligan a dormir en las islas (policies.json
    `courses_overnight_requirement`); la lista a mano solo tenia paquetes."""
    assert {"open_water", "advanced", "4_dives_2_days", "9_dives_4_days"} <= catalog.MULTI_DAY_SERVICES
    assert "2_dives_1_day" not in catalog.MULTI_DAY_SERVICES
    assert "3_dives_1_day" not in catalog.MULTI_DAY_SERVICES
    assert "minicourse" not in catalog.MULTI_DAY_SERVICES


def test_min_age_comes_from_the_activity_of_each_service():
    for service_id, service in catalog.SERVICES.items():
        activity = dom.activity_for_service(service_id)
        declared = _SERVICES_RAW[service_id].get("min_age")
        expected = declared if declared is not None else (activity.min_age if activity else None)
        assert service["min_age"] == expected, service_id
    assert catalog.SERVICES["divemaster"]["min_age"] == 18
    assert catalog.SERVICES["snorkeling"]["min_age"] == 6
    assert catalog.SERVICES["referral"]["min_age"] == 10  # antes None: completa un Open Water
