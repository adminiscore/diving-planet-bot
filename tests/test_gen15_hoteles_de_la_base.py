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
from src.config import settings

POLITICA = json.loads((Path(__file__).resolve().parents[1] / "data" / "knowledge_base" / "policies.json")
                      .read_text(encoding="utf-8-sig"))["policies"]["other_island_hotels"]


@pytest.mark.parametrize("hotel", ex.HOTELES_DE_LA_BASE)
def test_cada_hotel_sigue_en_la_base(hotel):
    """Una sola fuente: si la base deja de nombrar un hotel, la lista del bot tiene que cambiar con ella."""
    clave = hotel.replace("San Pedro de ", "")
    assert clave in POLITICA["es"] and clave in POLITICA["en"]


@pytest.mark.parametrize("flag", [False, True])
def test_el_extractor_los_conoce_con_el_flag(monkeypatch, flag):
    monkeypatch.setattr(settings, "hoteles_de_la_base", flag)
    assert ("Mulata" in ex._pistas_islas()) is flag
    assert ex.nombra_un_lugar("vamos a estar en Las Palmeras") is flag


@pytest.mark.parametrize("flag", [False, True])
def test_jev_los_nombra_en_la_opcion_islas(monkeypatch, flag):
    monkeypatch.setattr(settings, "hoteles_de_la_base", flag)
    monkeypatch.setattr(settings, "jev_lugar_cliente", True)
    pregunta = jev_router._questions_for_turn(None)[jev_router.CUSTOMER_PLACE]
    assert ("Eco Hotel Las Palmeras" in pregunta["criteria"]["islands"]) is flag
    assert "Eco Hotel Las Palmeras" not in pregunta["criteria"]["cartagena"]
