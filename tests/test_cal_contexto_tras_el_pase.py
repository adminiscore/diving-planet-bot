"""CAL (17-oct, flag `contexto_tras_el_pase`): cuando la conversación ya está con una persona, el RAG lo sabe.

cal-14: el cliente pregunta si su reserva está confirmada; el bot pasa el caso a una persona porque no ve pagos. En el
turno siguiente el cliente pregunta "Vale, en concepto le coloco otros?" (el concepto de una transferencia) y el bot
se lo explica: improvisa sobre un pago que no ve y contradice la política ("fuera de ese caso no se paga por
transferencia"). Tras un pase, un "gracias" ya tenía su respuesta corta, pero una PREGUNTA seguía el flujo normal y el
RAG no sabía que el caso lo tiene un asesor.

El arreglo es un dato del estado en el contexto del RAG (el mismo patrón que la nota de DIVE TO HEAL): lo general se
contesta igual; lo de la reserva o el pago concreto del cliente lo confirma el asesor.
"""

import pytest

from src.agents import supervisor
from src.config import settings
from src.flows.state import ConversationState, Step


def _estado(paso: Step, idioma: str = "es") -> ConversationState:
    return ConversationState(conversation_id="t", language=idioma, step=paso)


@pytest.fixture
def flag(monkeypatch):
    def poner(valor: bool):
        monkeypatch.setattr(settings, "contexto_tras_el_pase", valor)
    return poner


def test_con_el_caso_en_manos_de_una_persona_el_rag_lo_sabe(flag):
    flag(True)
    contexto = supervisor._build_extra_context(_estado(Step.ESCALATE))
    assert "ya se pasó a una persona del equipo" in contexto
    assert "no lo deduzcas ni des instrucciones nuevas" in contexto
    assert "Las preguntas generales" in contexto, "lo general se sigue contestando"
    en = supervisor._build_extra_context(_estado(Step.ESCALATE, "en"))
    assert "already been passed to a person" in en


def test_sin_pase_no_hay_nota(flag):
    flag(True)
    assert "ya se pasó a una persona" not in (supervisor._build_extra_context(_estado(Step.FREE_TEXT)) or "")


def test_sin_el_flag_no_cambia_nada(flag):
    flag(False)
    assert "ya se pasó a una persona" not in (supervisor._build_extra_context(_estado(Step.ESCALATE)) or "")
