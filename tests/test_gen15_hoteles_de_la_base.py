"""gen-15 (21-oct), flag `hoteles_de_la_base`: el extractor y Jev conocen los hoteles de las islas que da la base.

Banco docs/robustness/gen/banco_gen15_hoteles.py (11 frases ×3): extractor 19/33 → 29/33, Jev 15/33 → 30/33 (Majagua,
Eco Hotel Las Palmeras, Mulata, Rosario de Mar y Ubuntu → islands); los controles (Barú, «ir a las islas a bucear»)
igual.
"""

import json
from pathlib import Path

import pytest

from src.agents import extractor_turno as ex
from src.agents import jev_router

POLITICA = json.loads((Path(__file__).resolve().parents[1] / "data" / "knowledge_base" / "policies.json")
                      .read_text(encoding="utf-8-sig"))["policies"]["other_island_hotels"]


@pytest.mark.parametrize("hotel", ex.HOTELES_DE_LA_BASE)
def test_cada_hotel_sigue_en_la_base(hotel):
    """Una sola fuente: si la base deja de nombrar un hotel, la lista del bot tiene que cambiar con ella."""
    clave = hotel.replace("San Pedro de ", "")
    assert clave in POLITICA["es"] and clave in POLITICA["en"]


def test_el_extractor_los_conoce():
    assert "Mulata" in ex._pistas_islas()
    assert ex.nombra_un_lugar("vamos a estar en Las Palmeras")


def test_jev_los_nombra_en_la_opcion_islas():
    pregunta = jev_router._questions_for_turn(None)[jev_router.CUSTOMER_PLACE]
    assert "Eco Hotel Las Palmeras" in pregunta["criteria"]["islands"]
    assert "Eco Hotel Las Palmeras" not in pregunta["criteria"]["cartagena"]


@pytest.mark.parametrize("lugar, pregunta", [
    ({"choice": "islands", "confidence": 0.97}, False),
    ({"choice": "cartagena", "confidence": 0.9}, False),
    ({"choice": "islands", "confidence": 0.3}, True),   # Jev no está seguro: la puerta de siempre
    ({"choice": "none", "confidence": 0.9}, True),
])
def test_la_puerta_del_origen_no_pregunta_si_jev_esta_seguro(lugar, pregunta):
    """«We booked 3 nights at Mulata. How much is snorkeling?»: la puerta del origen preguntaba con Jev seguro."""
    from src.agents import conversational_core as core
    from src.flows.state import ConversationState

    st = ConversationState(conversation_id="gen15", language="en")
    st._jev_lugar = lugar
    st._jev_pide_precio = True
    texto = core._origen_antes_del_precio(st, "We booked 3 nights at Mulata. How much is snorkeling?",
                                          "Snorkeling costs 45 USD online.")
    assert (texto is not None) is pregunta
