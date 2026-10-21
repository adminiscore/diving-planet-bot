"""gen-3b (21-oct, decisiones de Gadea): pasar DIRECTAMENTE a un asesor cuando toca, en vez de ofrecerlo.
(1) `cambio_de_reserva_pasa`: cambiar la fecha, cancelar o cambiar el número de personas de una reserva ya hecha.
(2) `privado_pasa_directo`: el servicio privado, en cuanto lo pide (Jev `pide_servicio_privado`)."""
import pytest

from src.agents import jev_router as jr
from src.agents.rutas import changes
from src.agents.rutas.info import pide_servicio_privado
from src.config import settings
from src.flows.state import ConversationState, Step
from src.orchestration.router import classify_route
from src.orchestration.state import ROUTE_INFO


def _state(lang: str = "es") -> ConversationState:
    st = ConversationState(conversation_id="gen3b", language=lang)
    st.detected_language = lang
    return st


@pytest.mark.parametrize("kind", ["reschedule", "cancellation", "modify_headcount"])
@pytest.mark.parametrize("lang", ["es", "en"])
def test_con_el_flag_un_cambio_de_reserva_pasa_directo(monkeypatch, kind, lang):
    monkeypatch.setattr(settings, "cambio_de_reserva_pasa", True)
    st = _state(lang)
    mensaje = "Tengo reserva para mañana y necesito cambiarla al viernes, somos 3"
    respuesta = changes._booking_change_response(st, mensaje, kind)
    assert st.step == Step.ESCALATE and st.pending_escalation_reason and st.quick_replies == []
    assert ("Te paso ahora con un asesor" if lang == "es" else "I'm passing you now") in respuesta
    assert "menú principal" not in respuesta and "main menu" not in respuesta and "?" not in respuesta.split("\n")[-1]
    # El asesor lee el mensaje que provocó el pase.
    assert mensaje[:60] in st.pending_note
    assert [h["role"] for h in st.history] == ["user", "assistant"]


def test_apagado_sigue_ofreciendo_con_botones(monkeypatch):
    monkeypatch.setattr(settings, "cambio_de_reserva_pasa", False)
    st = _state()
    respuesta = changes._booking_change_response(st, "quiero cambiar la fecha de mi reserva", "reschedule")
    assert st.pending_escalation_reason is None and len(st.quick_replies) == 2
    assert respuesta.rstrip().endswith("?")


def test_la_pregunta_de_jev_solo_va_con_el_flag(monkeypatch):
    monkeypatch.setattr(settings, "privado_pasa_directo", False)
    assert jr.PIDE_SERVICIO_PRIVADO not in jr._questions_for_turn()
    monkeypatch.setattr(settings, "privado_pasa_directo", True)
    assert jr.PIDE_SERVICIO_PRIVADO in jr._questions_for_turn()
    assert jr.answers_to_signals({jr.PIDE_SERVICIO_PRIVADO: {"type": "noul", "noul": 0.9}})[
        jr.PIDE_SERVICIO_PRIVADO] is True
    assert jr.answers_to_signals({jr.PIDE_SERVICIO_PRIVADO: {"type": "noul", "noul": 0.2}})[
        jr.PIDE_SERVICIO_PRIVADO] is False


def test_privado_por_jev_va_a_info_solo_con_el_flag(monkeypatch):
    mensaje = "¿Podemos tener la lancha solo para nosotros seis el sábado?"
    senales = {jr.PIDE_SERVICIO_PRIVADO: True}
    monkeypatch.setattr(settings, "privado_pasa_directo", False)
    assert not pide_servicio_privado(mensaje.lower(), senales)
    monkeypatch.setattr(settings, "privado_pasa_directo", True)
    assert pide_servicio_privado(mensaje.lower(), senales)
    assert classify_route(_state(), mensaje, senales) == ROUTE_INFO
    # La lista de siempre sigue valiendo sin Jev.
    assert pide_servicio_privado("queremos un evento corporativo", {})


async def test_el_nodo_info_pasa_y_el_resumen_lleva_el_mensaje(monkeypatch):
    from src.agents.info_agent import info_node

    monkeypatch.setattr(settings, "privado_pasa_directo", True)
    monkeypatch.setattr(settings, "grupo_privado_pase", True)
    st = _state()
    mensaje = "¿Podemos tener la lancha solo para nosotros seis el sábado?"
    out = await info_node({"conv_state": st, "message": mensaje, "signals": {jr.PIDE_SERVICIO_PRIVADO: True}})
    assert "Te paso con un asesor" in out["reply"]
    assert st.step == Step.ESCALATE and mensaje in st.pending_note
    assert [h["role"] for h in st.history] == ["user", "assistant"]
