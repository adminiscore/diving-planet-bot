"""ARQ-1l (22-oct, flag `adaptado_contesta_lo_demas`): con DIVE TO HEAL activo, lo que el mensaje pregunta aparte del
buceo adaptado lo contesta el RAG antes del texto fijo del asesor (precio a medida: decisión del dueño del 17-jul)."""
import asyncio

from src.agents import escalation_agent as esc
from src.agents.rutas.safety import _adaptive_diving_advisor_answer
from src.flows.state import ConversationState


def _conv() -> ConversationState:
    st = ConversationState(conversation_id="arq1l", language="es")
    st.adaptive_diving_context = True
    return st


def test_con_el_flag_lo_demas_va_delante(monkeypatch):
    vistos = []

    async def lo_demas(conv, message, tema, key, reason):
        vistos.append(tema)
        return "El acompañante cuesta 80 USD online."

    monkeypatch.setattr(esc, "_contestar_lo_demas", lo_demas)
    texto = asyncio.run(esc.respuesta_dive_to_heal(_conv(), "¿y el acompañante cuánto paga?"))
    assert texto.startswith("El acompañante cuesta 80 USD") and texto.endswith(_adaptive_diving_advisor_answer("es"))
    assert "buceo adaptado" in vistos[0]


def test_si_no_pregunta_nada_mas_solo_el_texto_fijo(monkeypatch):

    async def nada(conv, message, tema, key, reason):
        return None

    monkeypatch.setattr(esc, "_contestar_lo_demas", nada)
    assert asyncio.run(esc.respuesta_dive_to_heal(_conv(), "¿cuánto cuesta?")) == _adaptive_diving_advisor_answer("es")
