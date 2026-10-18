"""Tras pasar la conversación a una persona (13-oct, `cambio-fecha-por-enfermedad`, rondas ex8-B2 y ex7-B):

1. `aviso_medico_dice_pase`: el aviso médico pasa a una persona (Step.ESCALATE) pero no lo decía.
2. `tras_pase_sin_vender`: con la conversación ya pasada, el bot no vuelve a hacer la pregunta de la reserva ("Which one
   are you leaning toward — diving, a mini-course…?") cuando el cliente da un dato; contesta lo que se pregunte o deja
   una nota corta.
"""
from unittest.mock import AsyncMock

import pytest

from src.agents import conversational_core as core
from src.agents import escalation, supervisor
from src.agents.supervisor import route_message
from src.config import settings
from src.flows.state import ConversationState, Step


@pytest.mark.parametrize("flag,dice", [(True, True), (False, False)])
def test_el_aviso_medico_dice_que_pasa_a_una_persona(monkeypatch, flag, dice):
    monkeypatch.setattr(settings, "aviso_medico_dice_pase", flag)
    _, es = escalation.sensitive_response_for("medical_questions", "es")
    _, en = escalation.sensitive_response_for("medical_questions", "en")
    assert ("Te paso ahora" in es) is dice and ("I'm passing you now" in en) is dice
    # los demás avisos no cambian
    _, tiempo = escalation.sensitive_response_for("weather_conditions", "es")
    assert "Te paso ahora" not in tiempo


@pytest.fixture
def offline(monkeypatch):
    for name in ("fill_gaps", "detect_special_signals", "resolve_slot_answer"):
        monkeypatch.setattr(core, name, AsyncMock(return_value={}))
    monkeypatch.setattr(core, "extract_notes", AsyncMock(return_value=[]))
    monkeypatch.setattr(core, "compose_acknowledgement", AsyncMock(return_value=""))
    monkeypatch.setattr(settings, "notes_in_parallel", False)
    monkeypatch.setattr(settings, "ack_in_parallel", False)
    monkeypatch.setattr(core, "lanzar_rag_adelantado", lambda *a, **k: None)  # rag-5: sin respuesta adelantada
    monkeypatch.setattr(supervisor, "rag_answer", AsyncMock(return_value="RESPUESTA_RAG"))

    async def _senales(message, **_k):
        return {}

    monkeypatch.setattr(supervisor, "detect_routing_signals", _senales)


def _pasada(lang="en") -> ConversationState:
    st = ConversationState(conversation_id="pasada", language=lang)
    st.step = Step.ESCALATE
    st.detected_language = lang
    return st


@pytest.mark.parametrize("flag", [True, False])
async def test_tras_el_pase_no_vuelve_a_vender(monkeypatch, offline, flag):
    monkeypatch.setattr(settings, "tras_pase_sin_vender", flag)
    st = _pasada()
    resp = await route_message(st, "We already have a room booked on the island for Monday and Tuesday night")
    vende = any(p in resp.lower() for p in ("leaning toward", "mini-course", "how many", "where would you"))
    if flag:
        assert not vende, resp
        assert "advisor" in resp.lower() or "RESPUESTA_RAG" in resp
    else:
        assert vende, resp  # la conducta de antes: vuelve la pregunta de la reserva


# --- 3. posventa: el cliente ya tiene una reserva o ya hizo la actividad ------------------------------------------

@pytest.mark.parametrize("flag,ahora,antes,afirma,queda", [
    (True, True, False, None, True),     # Jev dice que ya tiene reserva
    (True, None, True, None, True),      # se recuerda en los turnos siguientes
    (True, False, True, True, False),    # elige una actividad nueva: vuelve la reserva
    (True, None, False, None, False),
    (False, True, False, None, False),   # flag apagado
])
def test_modo_posventa(monkeypatch, flag, ahora, antes, afirma, queda):
    monkeypatch.setattr(settings, "posventa_sin_vender", flag)
    st = ConversationState(conversation_id="posventa")
    st.ya_reservado = antes
    senales = {k: v for k, v in (("ya_reservado", ahora), ("affirms_activity", afirma)) if v is not None}
    assert core._modo_posventa(st, senales) is queda


@pytest.mark.parametrize("flag", [True, False])
async def test_posventa_no_vende(monkeypatch, offline, flag):
    monkeypatch.setattr(settings, "posventa_sin_vender", flag)

    async def _senales(message, **_k):
        return {"ya_reservado": True}

    monkeypatch.setattr(supervisor, "detect_routing_signals", _senales)
    st = ConversationState(conversation_id="waivers", language="en")
    st.step = Step.FREE_TEXT
    st.detected_language = "en"
    resp = await route_message(st, "Just completed the waivers. Thank you!")
    vende = any(p in resp.lower() for p in ("leaning toward", "mini-course", "what would you like to experience"))
    assert vende is (not flag), resp


def test_posventa_no_corta_una_reserva_nueva_en_curso(monkeypatch):
    """Ronda atencion-B2: a mitad de reservar snorkel, "ok ya he buceado con ustedes" (Jev: ya_reservado) no pasa a
    posventa; sin actividad elegida (cambio de fecha, fotos) sí; y tras mandar el enlace, también."""
    monkeypatch.setattr(settings, "posventa_sin_vender", True)
    st = ConversationState(conversation_id="posventa")
    st.detected_activity = "snorkel"
    assert core._modo_posventa(st, {"ya_reservado": True}) is False
    st.history = [{"role": "assistant", "content": "Reserva aquí: https://book.divingplanet.org/snorkel"}]
    assert core._modo_posventa(st, {"ya_reservado": True}) is True
    nuevo = ConversationState(conversation_id="posventa2")
    assert core._modo_posventa(nuevo, {"ya_reservado": True}) is True

