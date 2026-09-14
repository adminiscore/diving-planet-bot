"""F3b del plan de dominio de actividades (docs/robustness/activity-domain-plan.md).

Los textos que ve el cliente sobre cada actividad vivian en seis tablas repartidas
por el nucleo, el RAG y la elegibilidad, cada una con su propio vocabulario de
claves. Ahora viven en el registro (`texts` de activities.json), una variante por
uso, y el codigo las lee de ahi. Se migraron copiando los textos literalmente
(94 salidas visibles comparadas antes/despues, identicas); estos tests fijan que
las tablas no vuelven y que cada consumidor usa el texto del registro.
"""

import pytest

from src.agents import conversational_core as core
from src.agents import rag_agent
from src.domain import activities as dom
from src.flows import eligibility
from src.flows.state import ConversationState

LANGS = ["es", "en"]


def test_hand_written_text_tables_are_gone():
    for module, names in (
        (core, ("_DELIB_LABELS_ES", "_DELIB_LABELS_EN", "_OFFERING_TO_SERVICE",
                "_OFFERING_BLURB_ES", "_OFFERING_BLURB_EN", "_RECALL_LABELS_ES", "_RECALL_LABELS_EN")),
        (rag_agent, ("_PRICE_CATALOG_LABELS_ES", "_PRICE_CATALOG_LABELS_EN")),
        (eligibility, ("_ACTIVITY_LABELS",)),
    ):
        for name in names:
            assert not hasattr(module, name), f"{module.__name__}.{name} volvio"


def test_course_mentions_use_registry_ids():
    assert set(core._COURSE_MENTION_RE) <= set(dom.activity_ids())


@pytest.mark.parametrize("lang", LANGS)
def test_comparison_uses_registry_names_and_pitches(lang):
    offerings = core._mentioned_offerings("open water o advanced")
    query = core._comparison_query(offerings, lang)
    composed = core._compose_comparison(offerings, lang)
    for activity_id in offerings:
        assert dom.text(activity_id, "name_in_sentence", lang) in query
        assert dom.text(activity_id, "pitch", lang) in composed


@pytest.mark.parametrize("lang", LANGS)
def test_generic_course_is_compared_as_its_default_level(lang):
    """padi_course se compara como Open Water (regla del owner, `default_level`)."""
    composed = core._compose_comparison(["padi_course"], lang)
    open_water = dom.by_id("padi_open_water").services["cartagena"][0]
    from src.flows.catalog import SERVICES

    assert SERVICES[open_water]["name_es" if lang == "es" else "name_en"] in composed


@pytest.mark.parametrize("lang", LANGS)
def test_recall_answer_uses_registry_recall_text(lang):
    state = ConversationState(conversation_id="texts-recall")
    state.language = lang
    state.detected_activity = "padi_open_water"
    assert dom.text("padi_open_water", "recall", lang) in core._recall_answer(state, "activity")


@pytest.mark.parametrize("lang", LANGS)
def test_price_answer_uses_registry_price_label(lang):
    answer = rag_agent._canonical_price_named_services_answer("cuanto cuesta el snorkel?", lang)
    assert dom.text("snorkel", "price_label", lang) in answer


@pytest.mark.parametrize("lang", LANGS)
def test_group_plan_uses_registry_plan_labels(lang):
    text = eligibility.format_group_plan(eligibility.plan_group(noncert_ages=[9]), lang)
    assert dom.text("bubble_makers", "plan_label", lang) in text
