"""gen-2 (20-oct, fase GEN; docs/robustness/gen/gen2-diagnostico.md): "inventa o da por hecho".

- `pregunta_sola_con_su_sitio`: la pregunta sola de la búsqueda doble deja el sitio si la pregunta trata de él
  ("estoy en Barú, ¿me recogen en el hotel?").
- `abre_con_la_respuesta`: el RAG no abre con "¡Claro que sí!" delante de un "no" o un "depende".
- La base: la recogida es solo en las Islas del Rosario (Barú no), en Cartagena no se recoge en el hotel, los cursos de
  2 días piden al menos una noche, y el pago presencial tiene formas de preguntarlo."""

import json
from pathlib import Path

import pytest

from src.agents import query_rewriter as qr
from src.agents.rag_agent import build_system_prompt
from src.config import settings
from src.prompts.info import RAG_ABRE_CON_LA_RESPUESTA_ES

BASE = Path("data/knowledge_base")


@pytest.mark.parametrize("flag", [True, False])
def test_la_pregunta_sola_deja_el_sitio_con_el_flag(monkeypatch, flag):
    monkeypatch.setattr(settings, "pregunta_sola_con_su_sitio", flag)
    assert ("deja ese lugar" in qr._instruccion_pregunta_sola("es")) is flag
    assert ("keep that place" in qr._instruccion_pregunta_sola("en")) is flag


@pytest.mark.parametrize("flag", [True, False])
def test_abre_con_la_respuesta(monkeypatch, flag):
    monkeypatch.setattr(settings, "rag_no_adivina", True)
    monkeypatch.setattr(settings, "abre_con_la_respuesta", flag)
    assert (RAG_ABRE_CON_LA_RESPUESTA_ES in build_system_prompt("es")) is flag


def test_la_base_dice_lo_que_es_no():
    pol = json.loads((BASE / "policies.json").read_text(encoding="utf-8"))["policies"]
    assert "Barú no es parte de las islas" in pol["island_pickup"]["es"] and "Barú is not part" in pol["island_pickup"]["en"]
    assert "no hay recogida en el hotel" in pol["meeting_point"]["es"]
    assert "al menos una noche" in pol["courses_overnight_requirement"]["es"]
    formas = json.loads((BASE / "curada/preguntas.json").read_text(encoding="utf-8"))["reglas"]
    assert any("efectivo" in f for f in formas["politica:foreign_card_payment"]["es"])


@pytest.mark.parametrize("flag", [True, False])
def test_sin_genero_supuesto(monkeypatch, flag):
    """gen-12 (21-oct): el RAG no da por hecho si el cliente es hombre o mujer."""
    from src.prompts.info import RAG_SIN_GENERO_ES

    monkeypatch.setattr(settings, "rag_no_adivina", True)
    monkeypatch.setattr(settings, "sin_genero_supuesto", flag)
    assert (RAG_SIN_GENERO_ES in build_system_prompt("es")) is flag


def test_la_base_no_nombra_el_sistema_interno():
    """gen-12 (21-oct): «ROVERD» es el nombre interno del sistema de reservas (criterio sin-fugas)."""
    for f in ("policies.json", "discounts.json", "curada/faqs.json", "curada/preguntas.json"):
        assert "roverd" not in (BASE / f).read_text(encoding="utf-8-sig").lower(), f
