"""Flag `rag_plan_nombrado` (s4-27, 7-oct): si el cliente NOMBRA cuántas inmersiones y su origen consta, el contexto
del RAG dice qué plan del catálogo es.

Caso: `precio-desde-islas-vs-cartagena`, "¿el precio de las 2 inmersiones? desde ese hotel" con el cliente ya en las
islas: el RAG ofrecía el paquete de 3 y negaba que hubiera 2 inmersiones sueltas desde las islas (existe: 124 USD).
Se fija: qué plan sale por número y origen, que no sale nada sin origen / sin número de inmersiones / con el flag
apagado / con ese plan ya elegido, y que la línea llega al contexto del RAG por `_entradas_rag`.
"""
import pytest

from src.agents import conversational_core as core
from src.config import settings
from src.flows.state import ConversationState


def _estado(location, lang="es", selected=None) -> ConversationState:
    s = ConversationState(conversation_id="plan-nombrado", language=lang)
    s.location = location
    s.selected_service = selected
    return s


@pytest.mark.parametrize("location,lang,mensaje,esperado", [
    ("island", "es", "Me puedes decir el precio de las 2 inmersiones? Desde ese hotel?", ["124 USD"]),
    ("cartagena", "es", "¿Y en el caso de tomar solo 2 inmersiones desde Cartagena?", ["178 USD"]),
    ("cartagena", "en", "Do you have just two dives, so I only do one day?", ["Fun Dives - 2 dives (1 day)"]),
    ("cartagena", "es", "quiero el paquete de 5 buceos", ["Paquete de 5 inmersiones (2 dias)", "392 USD"]),
    ("island", "es", "¿y el de 4 buceos?", ["4 diurnas", "3 diurnas + 1 nocturna"]),  # las dos variantes
])
def test_sale_el_plan_del_numero_y_el_origen(monkeypatch, location, lang, mensaje, esperado):
    monkeypatch.setattr(settings, "rag_plan_nombrado", True)
    linea = core._plan_nombrado(_estado(location, lang), mensaje)
    assert linea and all(e in linea for e in esperado)
    otro = "ya en las islas" if location == "cartagena" else "(1 día):"
    assert otro not in linea  # solo los planes de SU origen


@pytest.mark.parametrize("flag,location,mensaje,selected", [
    (False, "island", "el precio de las 2 inmersiones", None),          # flag apagado
    (True, None, "el precio de las 2 inmersiones", None),               # el origen no consta (lo pregunta la opción C)
    (True, "island", "somos 2 personas", None),                         # el número no es de inmersiones
    (True, "cartagena", "hice 20 inmersiones el año pasado", None),     # ningún plan de 20
    (True, "island", "el precio de las 2 inmersiones", "2_dives_1_day_already_on_island"),  # ya elegido: va su ficha
])
def test_no_sale_nada(monkeypatch, flag, location, mensaje, selected):
    monkeypatch.setattr(settings, "rag_plan_nombrado", flag)
    assert core._plan_nombrado(_estado(location, selected=selected), mensaje) is None


def test_llega_al_contexto_del_rag(monkeypatch):
    monkeypatch.setattr(settings, "rag_plan_nombrado", True)
    st = _estado("island")
    entradas = core._entradas_rag(st, [], "¿cuánto valen las 2 inmersiones?")
    assert "124 USD" in entradas["extra_context"]
    monkeypatch.setattr(settings, "rag_plan_nombrado", False)
    assert "124 USD" not in (core._entradas_rag(st, [], "¿cuánto valen las 2 inmersiones?")["extra_context"] or "")
