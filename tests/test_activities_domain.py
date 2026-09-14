"""F1 del plan de dominio de actividades (docs/robustness/activity-domain-plan.md).

El registro es la fuente unica; estos tests son la barrera que impide que vuelva a
desincronizarse del catalogo. Leen los ficheros de datos REALES, no copias: si
negocio edita `services.json` o `activities.json` y rompe la coherencia, falla la CI.
"""

import pytest

from src.domain import activities as dom


def test_registry_is_coherent_with_the_catalog():
    problems = dom.validate()
    assert not problems, "activities.json incoherente:\n- " + "\n- ".join(problems)


def test_every_sellable_service_has_exactly_one_activity():
    """Sustituye a SERVICE_TO_CART_TYPE/ISLAND_SERVICE_MAP escritos a mano: el
    catalogo entero queda cubierto, incluidas las variantes de isla que esos mapas
    no tenian (3 y 4 inmersiones)."""
    for service_id in ("3_dives_1_day_already_on_island", "4_dives_2_days_already_on_island",
                       "4_dives_2_days_mixed_already_on_island"):
        assert dom.activity_for_service(service_id).id == "certified_diving"


def test_each_specialty_is_its_own_activity():
    """Decision del owner (2026-09-14): una actividad por especialidad."""
    specialties = [a for a in dom.registry().activities if a.family == "specialty" and not a.generic]
    services = [s for a in specialties for s in a.services["cartagena"]]
    assert len(services) == len(set(services)) == len(specialties)


def test_generic_activities_resolve_through_context_not_services():
    for activity_id in ("padi_course", "padi_specialty"):
        activity = dom.by_id(activity_id)
        assert activity.generic and not activity.all_services()


@pytest.mark.parametrize("lang", dom.LANGS)
def test_padi_course_context_tells_the_llm_how_to_pick_the_level(lang):
    """La decision del nivel la toma el LLM con este contexto (owner, 2026-09-14),
    no una regla en codigo: sin certificacion -> Open Water; solo probar un dia ->
    minicurso."""
    text = dom.by_id("padi_course").for_whom[lang]
    assert "`padi_open_water`" in text and "`minicourse`" in text


@pytest.mark.parametrize("lang", dom.LANGS)
def test_business_context_covers_every_activity_once(lang):
    context = dom.business_context(lang)
    for activity_id in dom.activity_ids():
        assert context.count(f"`{activity_id}` —") == 1


def test_business_context_can_be_restricted():
    context = dom.business_context("es", ["minicourse", "snorkel"])
    assert "`minicourse`" in context and "`snorkel`" in context
    assert "`padi_open_water` —" not in context


def test_bookable_activities_exclude_add_ons_and_activities_without_service():
    bookable = dom.bookable_activity_ids()
    assert "refresher" not in bookable          # se vende como el minicurso
    assert "bubble_makers" not in bookable      # sin servicio en el catalogo (D2)
    assert {"padi_course", "padi_specialty"} <= set(bookable)   # genericas: F4 pregunta el nivel
    assert {"specialty_nitrox", "padi_open_water_referral", "certified_diving"} <= set(bookable)


def test_lookups():
    assert dom.service_ids("minicourse", "island") == ("minicourse_already_on_island",)
    assert dom.label("snorkel", "en") == "Snorkeling"
    assert dom.label("no_existe", "es") == "no_existe"
    assert dom.activity_for_service("private") is None
