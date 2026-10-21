"""ord-9 (21-oct, flag `listas_del_dato`, decisión de Gadea tras G10 de control): si Jev dice que el cliente pregunta qué
incluye un plan y el plan es uno solo, el RAG no enumera (`sin_lista`) y el código añade la lista exacta de la ficha."""
import pytest

from src.agents import conversational_core as cc
from src.agents import jev_router
from src.config import settings
from src.flows.state import ConversationState

RAG = "¡Claro! El minicurso es perfecto para empezar.\n\n¿Quieres que te pase el enlace?"


@pytest.fixture
def con_flag(monkeypatch):
    monkeypatch.setattr(settings, "listas_del_dato", True)


def _conv(lang="es", pide=True, **campos) -> ConversationState:
    st = ConversationState(conversation_id="ord9", language=lang)
    st._jev_pide_incluye = pide
    for k, v in campos.items():
        setattr(st, k, v)
    return st


@pytest.mark.parametrize("campos, esperado", [
    ({"actividad_preguntada": "minicourse", "location": "cartagena"}, "minicourse"),
    ({"actividad_preguntada": "minicourse", "location": "island"}, "minicourse_already_on_island"),
    ({"selected_service": "open_water", "location": "island"}, "open_water_already_on_island"),
    ({"actividad_preguntada": "minicourse"}, None),                        # sin origen: no hay un plan solo
    ({"actividad_preguntada": "certified_diving", "location": "cartagena"}, None),  # varios planes
])
def test_el_plan_concreto(campos, esperado):
    from src.flows.catalog import SERVICES

    servicio = cc._servicio_concreto(_conv(**campos))
    assert (servicio is SERVICES.get(esperado)) if esperado else servicio is None


def test_la_lista_exacta_va_antes_de_la_pregunta(con_flag):
    texto = cc._con_lista_del_dato(_conv(actividad_preguntada="minicourse", location="cartagena"), RAG)
    parrafos = texto.split("\n\n")
    assert "incluye:" in parrafos[1] and "Almuerzo" in parrafos[1] and "Seguro obligatorio de buceo" in parrafos[1]
    assert parrafos[-1].endswith("?")


def test_en_ingles(con_flag):
    texto = cc._con_lista_del_dato(_conv("en", actividad_preguntada="padi_open_water", location="cartagena"),
                                   "Sure! Do you want the link?")
    assert "includes:" in texto and "Lunch on day 1" in texto


@pytest.mark.parametrize("campos", [
    {"pide": False, "actividad_preguntada": "minicourse", "location": "cartagena"},  # Jev: no pregunta qué incluye
    {"actividad_preguntada": "minicourse"},                                          # sin plan concreto
])
def test_cuando_no_toca_no_cambia(con_flag, campos):
    assert cc._con_lista_del_dato(_conv(**campos), RAG) == RAG


def test_apagado_no_cambia(monkeypatch):
    monkeypatch.setattr(settings, "listas_del_dato", False)
    assert cc._con_lista_del_dato(_conv(actividad_preguntada="minicourse", location="cartagena"), RAG) == RAG


def test_el_rag_recibe_sin_lista_y_la_huella_lo_distingue(con_flag):
    st = _conv(actividad_preguntada="minicourse", location="cartagena")
    con = cc._entradas_rag(st, [], "¿qué incluye el minicurso?")
    assert con.get("sin_lista") is True
    st._jev_pide_incluye = False
    sin = cc._entradas_rag(st, [], "¿qué incluye el minicurso?")
    assert "sin_lista" not in sin
    assert cc._huella_rag("m", con) != cc._huella_rag("m", sin)


def test_jev_solo_pregunta_con_el_flag(monkeypatch):
    monkeypatch.setattr(settings, "listas_del_dato", False)
    assert jev_router.PIDE_QUE_INCLUYE not in jev_router._questions_for_turn()
    monkeypatch.setattr(settings, "listas_del_dato", True)
    assert jev_router.PIDE_QUE_INCLUYE in jev_router._questions_for_turn()
    assert jev_router.answers_to_signals({jev_router.PIDE_QUE_INCLUYE: {"noul": 0.9}})[jev_router.PIDE_QUE_INCLUYE]


@pytest.mark.asyncio
async def test_si_la_respuesta_se_escribio_sin_la_indicacion_se_rehace(con_flag, monkeypatch):
    """La adelantada sale antes que Jev y que la extracción: si al terminar toca la lista, se rehace con sin_lista."""
    from src.agents import supervisor

    llamadas = []

    async def _rag(query, **kw):
        llamadas.append(kw)
        return "Respuesta sin enumerar."
    monkeypatch.setattr(supervisor, "rag_answer", _rag)
    st = _conv(actividad_preguntada="minicourse", location="cartagena")
    texto = await cc._sin_lista_si_hace_falta(st, "¿qué incluye?", "Incluye lancha y equipo.", {"lang": "es"})
    assert texto == "Respuesta sin enumerar." and llamadas[0]["sin_lista"] is True
    # Con la indicación ya puesta, o sin lista que añadir, no se rehace.
    assert await cc._sin_lista_si_hace_falta(st, "q", "A", {"sin_lista": True}) == "A"
    st._jev_pide_incluye = False
    assert await cc._sin_lista_si_hace_falta(st, "q", "A", {}) == "A"
    assert len(llamadas) == 1
