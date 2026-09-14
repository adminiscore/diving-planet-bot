"""El refresher SE COBRA (decision del owner, 2026-09-14): tarifa 2026 de
`pricing.json` "Minicurso de Buceo / Refresh".

El bot decia que era gratis en cuatro sitios (pregunta del flujo, nota de cierre,
respuesta canonica del RAG y contexto del LLM), contradiciendo la tarifa. El
precio NO se escribe en ningun sitio: sale del catalogo, del servicio con el que
se vende el refresher segun el registro de actividades (`sold_as: minicourse`).
"""

import json
from pathlib import Path

import pytest

from src.agents import conversational_core as core
from src.agents import rag_agent
from src.domain import activities as dom
from src.flows.catalog import SERVICES
from src.flows.state import ConversationState

_PRICING = Path(__file__).resolve().parents[1] / "data" / "knowledge_base" / "pricing.json"
_FREE_CLAIMS = ("sin coste adicional", "sin costo adicional", "no tiene costo adicional",
                "no extra cost", "at no extra cost", "no additional charge")


def _service(location):
    return SERVICES[dom.service_ids("refresher", location)[0]]


def _state(lang="es", location="cartagena"):
    state = ConversationState(conversation_id=f"refresher-{lang}-{location}")
    state.language = lang
    state.location = location
    return state


def _cop(value):
    return f"{int(value):,}".replace(",", ".")


def test_refresher_is_sold_as_the_minicourse_service():
    for location in dom.LOCATIONS:
        assert dom.service_ids("refresher", location) == dom.service_ids("minicourse", location)


@pytest.mark.parametrize(("location", "zone"), [("cartagena", "from_cartagena"), ("island", "from_islands")])
def test_the_catalog_service_carries_the_2026_refresh_tariff(location, zone):
    tariff = json.loads(_PRICING.read_text(encoding="utf-8-sig"))[zone]["servicios_buceo_snorkel"]["minicurso_refresh"]
    service = _service(location)
    assert service["price_cop"] == tariff["cop_online"]
    assert float(service["price_usd"]) == float(tariff["usd_online"])


@pytest.mark.parametrize("lang", ["es", "en"])
@pytest.mark.parametrize("location", ["cartagena", "island"])
def test_the_booking_flow_question_states_the_catalog_price(lang, location):
    text = core.ask_slot(_state(lang, location), core.SLOT_REFRESHER)
    service = _service(location)
    assert _cop(service["price_cop"]) in text
    assert str(int(round(float(service["price_usd"])))) in text
    assert not any(claim in text.lower() for claim in _FREE_CLAIMS)


@pytest.mark.parametrize("lang", ["es", "en"])
def test_the_closing_note_states_the_price_and_never_says_free(lang):
    state = _state(lang, "cartagena")
    state.refresher_interested = True
    note = core._refresher_note(state)
    assert _cop(_service("cartagena")["price_cop"]) in note
    assert not any(claim in note.lower() for claim in _FREE_CLAIMS)


def test_the_closing_note_is_empty_when_the_refresher_was_not_wanted():
    state = _state()
    state.refresher_interested = False
    assert core._refresher_note(state) == ""


@pytest.mark.parametrize(("lang", "question"), [
    ("es", "el refresher tiene costo adicional?"),
    ("en", "does the refresher cost extra?"),
])
def test_rag_answer_gives_both_catalog_prices(lang, question):
    answer = rag_agent._canonical_refresher_cost_answer(question, lang)
    assert answer
    for location in dom.LOCATIONS:
        assert _cop(_service(location)["price_cop"]) in answer
    assert not any(claim in answer.lower() for claim in _FREE_CLAIMS)


@pytest.mark.parametrize("lang", ["es", "en"])
def test_llm_context_no_longer_says_the_refresher_is_free(lang):
    """El contexto que se le pasa al LLM para un acompañante certificado pero
    inactivo afirmaba "sin coste adicional"; el LLM lo repetia al cliente."""
    from src.agents import supervisor

    state = _state(lang)
    state.history = [{"role": "user", "content": "mi amigo se certifico hace 8 años y no ha vuelto a bucear"}]
    context = supervisor._build_extra_context(state) or ""
    assert "refresher" in context.lower()
    assert not any(claim in context.lower() for claim in _FREE_CLAIMS)
