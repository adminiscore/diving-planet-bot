"""gen-13 (21-oct, flag `contesta_antes_de_cualquier_pase`): al pasar a un asesor por CUALQUIER motivo, las otras
preguntas del mensaje se contestan delante del pase (causa 2 de G10/G9: el pase se comía el resto del mensaje).

Un solo sitio: el cierre del turno en `supervisor.route_message`, con `escalation_agent.lo_contestable_en_cualquier_pase`.
"""
import pytest

from src.agents import escalation_agent, supervisor
from src.flows.state import ConversationState, Step

PASE = "Te paso con un asesor del equipo, que te escribe por aquí enseguida."
LO_DEMAS = "El minicurso desde Cartagena cuesta 655.000 COP e incluye el equipo."


def _conv(**campos) -> ConversationState:
    st = ConversationState(conversation_id="gen13", language="es")
    for k, v in campos.items():
        setattr(st, k, v)
    return st


def _turno_que_pasa(motivo: str, senales: dict):
    """Un turno del grafo que pasa a un asesor con `motivo` y deja las señales del router."""
    async def _grafo(state, message):
        state._senales_router = senales
        state.step = Step.ESCALATE
        state.pending_escalation_reason = motivo
        return PASE
    return _grafo


@pytest.fixture
def lo_demas(monkeypatch):
    llamadas = []

    async def _contestar(conv, message, tema, key, reason):
        llamadas.append({"tema": tema, "reason": reason, "paso": conv.step})
        return LO_DEMAS
    monkeypatch.setattr(escalation_agent, "_contestar_lo_demas", _contestar)
    return llamadas


async def _route(monkeypatch, motivo, senales, mensaje="pásame con alguien y ¿cuánto cuesta el minicurso?", **campos):
    monkeypatch.setattr("src.orchestration.graph.run_turn_via_graph", _turno_que_pasa(motivo, senales))
    st = _conv(**campos)
    return st, await supervisor.route_message(st, mensaje)


@pytest.mark.asyncio
async def test_un_pase_cualquiera_contesta_antes_lo_demas(monkeypatch, lo_demas):
    st, resp = await _route(monkeypatch, "solicitó asesor", {"asks_question": True})
    assert resp.startswith(LO_DEMAS) and resp.endswith(PASE)
    assert "solicitó asesor" in lo_demas[0]["tema"]


@pytest.mark.asyncio
async def test_el_rag_contesta_con_el_paso_de_antes_del_pase(monkeypatch, lo_demas):
    """Con el paso en ESCALATE el RAG diría «el asesor ya tiene tu caso» encima de «te paso ahora»."""
    st, _ = await _route(monkeypatch, "solicitó asesor", {"asks_question": True}, step=Step.MAIN_MENU)
    assert lo_demas[0]["paso"] == Step.MAIN_MENU
    assert st.step == Step.ESCALATE


@pytest.mark.asyncio
@pytest.mark.parametrize("motivo", ["datos sensibles detectados", "complaints_or_emergencies",
                                    "⚠️ FALLO TÉCNICO: OpenAI sin saldo o saturado (código 429)"])
async def test_los_pases_que_van_solos_no_contestan_nada_mas(monkeypatch, lo_demas, motivo):
    _, resp = await _route(monkeypatch, motivo, {"asks_question": True})
    assert resp == PASE and not lo_demas


@pytest.mark.asyncio
async def test_sin_pregunta_en_el_mensaje_el_pase_va_solo(monkeypatch, lo_demas):
    _, resp = await _route(monkeypatch, "solicitó asesor", {"asks_question": False}, mensaje="pásame con un asesor")
    assert resp == PASE and not lo_demas


@pytest.mark.asyncio
async def test_si_gen1_ya_contesto_no_se_repite(monkeypatch, lo_demas):
    async def _grafo(state, message):
        state._senales_router = {"asks_question": True}
        state._contestado_antes_del_pase = True  # lo hizo el nodo de escalado (médico o clima)
        state.step = Step.ESCALATE
        state.pending_escalation_reason = "medical_questions"
        return PASE
    monkeypatch.setattr("src.orchestration.graph.run_turn_via_graph", _grafo)
    resp = await supervisor.route_message(_conv(), "tengo asma, ¿y qué incluye el minicurso?")
    assert resp == PASE and not lo_demas


@pytest.mark.asyncio
async def test_un_turno_sin_pase_no_cambia(monkeypatch, lo_demas):
    async def _grafo(state, message):
        state._senales_router = {"asks_question": True}
        return "El minicurso cuesta 655.000 COP."
    monkeypatch.setattr("src.orchestration.graph.run_turn_via_graph", _grafo)
    resp = await supervisor.route_message(_conv(), "¿cuánto cuesta el minicurso?")
    assert resp == "El minicurso cuesta 655.000 COP." and not lo_demas
