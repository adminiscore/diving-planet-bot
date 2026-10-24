"""gen-2 (20-oct, fase GEN; docs/robustness/gen/gen2-diagnostico.md): "inventa o da por hecho".

- `abre_con_la_respuesta`: el RAG no abre con "¡Claro que sí!" delante de un "no" o un "depende".
- La base: la recogida es solo en las Islas del Rosario (Barú no), en Cartagena no se recoge en el hotel, los cursos de
  2 días piden al menos una noche, y el pago presencial tiene formas de preguntarlo."""

import json
from pathlib import Path

from src.agents.rag_agent import build_system_prompt
from src.prompts.info import RAG_ABRE_CON_LA_RESPUESTA_ES

BASE = Path("data/knowledge_base")


def test_abre_con_la_respuesta():
    assert RAG_ABRE_CON_LA_RESPUESTA_ES in build_system_prompt("es")


def test_la_base_dice_lo_que_es_no():
    pol = json.loads((BASE / "policies.json").read_text(encoding="utf-8"))["policies"]
    assert "Barú no es parte de las islas" in pol["island_pickup"]["es"] and "Barú is not part" in pol["island_pickup"]["en"]
    assert "no hay recogida en el hotel" in pol["meeting_point"]["es"]
    assert "al menos una noche" in pol["courses_overnight_requirement"]["es"]
    formas = json.loads((BASE / "curada/preguntas.json").read_text(encoding="utf-8"))["reglas"]
    assert any("efectivo" in f for f in formas["politica:foreign_card_payment"]["es"])


def test_sin_genero_supuesto():
    """gen-12 (21-oct): el RAG no da por hecho si el cliente es hombre o mujer."""
    from src.prompts.info import RAG_SIN_GENERO_ES

    assert RAG_SIN_GENERO_ES in build_system_prompt("es")


def test_la_base_no_nombra_el_sistema_interno():
    """gen-12 (21-oct): «ROVERD» es el nombre interno del sistema de reservas (criterio sin-fugas)."""
    for f in ("policies.json", "discounts.json", "curada/faqs.json", "curada/preguntas.json"):
        assert "roverd" not in (BASE / f).read_text(encoding="utf-8-sig").lower(), f
