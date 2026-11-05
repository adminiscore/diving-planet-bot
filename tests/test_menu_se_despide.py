"""#3300 (2b, 4-nov): «Entiendo, gracias. Entonces lo dejo para otra ocasión» recibía «¿Con cuál te animas?»."""
import asyncio

from src.agents import conversational_core as core
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


def test_se_despide_aunque_la_pregunta_pendiente_haya_cambiado(monkeypatch):
    """banco-se-despide, d-no-reservar: con el origen pendiente, «al final no vamos a reservar» recibía «¡Perfecto!» y el menú."""
    vistas = _con_escritor(monkeypatch)
    st = _estado(**{j.SE_DESPIDE: True})
    st.core_pending_slot = "location"
    assert _sin_dato(st) == "¡Claro, aquí estaremos! 🌊"
    assert vistas == [None] and st.quick_replies == []


def test_sin_despedida_y_con_la_pregunta_cambiada_sigue_el_flujo(monkeypatch):
    vistas = _con_escritor(monkeypatch)
    st = _estado(**{j.SE_DESPIDE: False})
    st.core_pending_slot = "location"
    assert _sin_dato(st) is None and vistas == []


def test_si_no_se_despide_sigue_la_pregunta(monkeypatch):
    vistas = _con_escritor(monkeypatch)
    st = _estado(**{j.SE_DESPIDE: False})
    assert _sin_dato(st) == f"¡Claro, aquí estaremos! 🌊\n\n{PREGUNTA}"
    assert vistas == [PREGUNTA] and st.quick_replies


def test_sin_la_senal_de_jev_es_la_conducta_de_hoy(monkeypatch):
    vistas = _con_escritor(monkeypatch)
    assert _sin_dato(_estado()) == f"¡Claro, aquí estaremos! 🌊\n\n{PREGUNTA}"
    assert vistas == [PREGUNTA]


def _pregunta_actividad(idioma="es", **campos):
    st = ConversationState(conversation_id="menu", language=idioma)
    for campo, valor in campos.items():
        setattr(st, campo, valor)
    return core.ask_slot(st, core.SLOT_ACTIVITY, reasking=True), st


def test_el_buzo_con_alguien_que_no_bucea_recibe_la_pregunta_de_los_dos():
    texto, st = _pregunta_actividad(is_certified=True, acompanante_sin_certificar=True)
    assert "para quien no bucea" in texto and "curso avanzado" not in texto and "paquete" not in texto
    assert len(st.quick_replies) == 3 and st.core_pending_slot == core.SLOT_ACTIVITY
    assert "companion" in _pregunta_actividad("en", is_certified=True, acompanante_sin_certificar=True)[0]


def test_el_buzo_solo_sigue_con_su_pregunta():
    assert "curso avanzado" in _pregunta_actividad(is_certified=True)[0]


def test_es_una_fila_de_la_tabla_y_su_duda_no_va_al_router():
    assert j.SE_DESPIDE in [s.nombre for s in j._DEL_TURNO]
    assert j.SE_DESPIDE in j._U34_QUESTIONS
    assert j.SE_DESPIDE in j._questions_for_turn(None)


def _listo_para_la_tarjeta(**senales) -> ConversationState:
    st = _estado(**senales)
    st.core_pending_slot = None
    st.location, st.is_colombian, st.detected_activity, st.detected_group_size = "cartagena", False, "snorkel", 2
    return st


def _turno(st):
    carry = {"prev_pending": None, "prev_main_activity": "snorkel"}
    return asyncio.run(sc._slotfill_close_phase(st, "Never mind then, thanks for your help.", "", False, carry))


def test_a_quien_se_despide_sin_pregunta_pendiente_no_le_sale_la_tarjeta(monkeypatch):
    """s05a (crucero): Jev veía la despedida y salía la tarjeta con su enlace."""
    _con_escritor(monkeypatch, "You're welcome! Enjoy Cartagena.")
    texto = _turno(_listo_para_la_tarjeta(**{j.SE_DESPIDE: True}))
    assert texto == "You're welcome! Enjoy Cartagena."


def test_si_no_se_despide_la_tarjeta_sale_como_siempre(monkeypatch):
    _con_escritor(monkeypatch)
    texto = _turno(_listo_para_la_tarjeta(**{j.SE_DESPIDE: False}))
    assert "book.divingplanet.org" in texto
