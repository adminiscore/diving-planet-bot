"""#3300 (2b, 4-nov): «Entiendo, gracias. Entonces lo dejo para otra ocasión» recibía «¿Con cuál te animas?»."""
import asyncio

from src.agents import jev_router as j
from src.agents.nucleo import slotfill_close as sc
from src.flows.state import ConversationState

PREGUNTA = "¿Con cuál te animas — *buceo*, *minicurso*, *snorkel* o un *curso PADI*? 🌊"


def _estado(**senales) -> ConversationState:
    st = ConversationState(conversation_id="despide", language="es")
    st.core_pending_slot = "activity"
    st._pregunta_del_escritor = PREGUNTA
    st._senales_router = senales
    st.quick_replies = [{"title": "Buceo", "value": "buceo"}]
    return st


def _con_escritor(monkeypatch, texto="¡Claro, aquí estaremos! 🌊"):
    vistas = []

    async def falso(state, message, history=None, **kw):
        vistas.append(state._pregunta_del_escritor)
        return texto

    monkeypatch.setattr(sc, "_rag_answer", falso)
    return vistas


def _sin_dato(st):
    return asyncio.run(sc._sin_dato(st, "lo dejo para otra ocasión", "activity", PREGUNTA))


def test_si_se_despide_no_lleva_la_pregunta_ni_sus_botones(monkeypatch):
    vistas = _con_escritor(monkeypatch)
    st = _estado(**{j.SE_DESPIDE: True})
    assert _sin_dato(st) == "¡Claro, aquí estaremos! 🌊"
    assert vistas == [None] and st.quick_replies == []


def test_si_no_se_despide_sigue_la_pregunta(monkeypatch):
    vistas = _con_escritor(monkeypatch)
    st = _estado(**{j.SE_DESPIDE: False})
    assert _sin_dato(st) == f"¡Claro, aquí estaremos! 🌊\n\n{PREGUNTA}"
    assert vistas == [PREGUNTA] and st.quick_replies


def test_sin_la_senal_de_jev_es_la_conducta_de_hoy(monkeypatch):
    vistas = _con_escritor(monkeypatch)
    assert _sin_dato(_estado()) == f"¡Claro, aquí estaremos! 🌊\n\n{PREGUNTA}"
    assert vistas == [PREGUNTA]


def test_es_una_fila_de_la_tabla_y_su_duda_no_va_al_router():
    assert j.SE_DESPIDE in [s.nombre for s in j._DEL_TURNO]
    assert j.SE_DESPIDE in j._U34_QUESTIONS
    assert j.SE_DESPIDE in j._questions_for_turn(None)
