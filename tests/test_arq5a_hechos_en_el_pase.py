"""arq-5a (23-oct, flag `hechos_en_el_pase`): el RAG de «contestar antes del pase» (asesor, pago, DIVE TO HEAL) recibe los
hechos del código, como en la ruta normal (G10 nº 5: ~15 fallos con hechos=None). Banco docs/robustness/arq/banco-arq5a.json.
"""

import pytest

from src.agents import conversational_core as core
from src.agents import escalation_agent as esc
from src.agents import supervisor
from src.config import settings
from src.flows.state import ConversationState


@pytest.mark.parametrize("flag", [False, True])
async def test_el_rag_antes_del_pase_recibe_los_hechos(monkeypatch, flag):
    monkeypatch.setattr(settings, "hechos_en_el_pase", flag)
    vistos = {}

    async def hechos(state, message, history, *, siempre=False):
        vistos["historial"], vistos["siempre"] = history, siempre
        state._hechos_del_rag = (["bloque"], ["incluye"])
        return "HECHOS"

    async def rag(message, **entradas):
        vistos["entradas"] = entradas
        return "El plan incluye el equipo."

    monkeypatch.setattr(core, "_hechos_para_el_rag", hechos)
    monkeypatch.setattr(supervisor, "rag_answer", rag)
    conv = ConversationState(conversation_id="arq5a", language="es")
    answer = await esc._contestar_lo_demas(conv, "¿qué incluye? y quiero hablar con alguien", "el pase", "es", "x")
    assert answer == "El plan incluye el equipo."
    assert ("hechos" in vistos["entradas"]) is flag
    if flag:
        assert vistos["entradas"]["hechos"] == "HECHOS" and vistos["entradas"]["hechos_bloques"] == (["bloque"], ["incluye"])
        assert vistos["siempre"] is True and vistos["historial"][-1]["content"].startswith("¿qué incluye?")


async def test_siempre_no_mira_si_el_mensaje_es_mezclado(monkeypatch):
    from src.agents import redactor_hechos

    llamadas = []

    async def turno(state, message, history):
        llamadas.append(message)
        return [{"actividad": "snorkel"}], ["incluye"]

    monkeypatch.setattr(redactor_hechos, "hechos_del_turno", turno)
    conv = ConversationState(conversation_id="arq5a", language="es")
    conv._otra_cosa = False  # Jev: todo es de la tabla, pero el turno va al asesor
    assert await core._hechos_para_el_rag(conv, "¿qué incluye?", []) is None
    assert await core._hechos_para_el_rag(conv, "¿qué incluye?", [], siempre=True)
    assert llamadas == ["¿qué incluye?"]
