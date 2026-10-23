"""Ronda mod-G (18-oct): dos arreglos del flujo vistos en las rondas mod-D y mod-F.

1. `recomendar_a_no_certificados`: con el extractor en Haiku, "Sería buzo principiante y snorkeling" no elige actividad
   (mensaje ambiguo; gpt-4.1-mini "adivinaba" minicurso) y el flujo repetía el menú entero, con "buceo" (solo para
   certificados). Sabiendo que NO es certificado, se le recomiendan SUS opciones y elige él (regla de Gadea).
2. `resolutor_sin_contradicciones`: "no, buceé hace poco" a "¿Eres buzo certificado?" fijaba "no certificado" →
   minicurso a 183 USD. Una respuesta que se contradice no fija el dato.
"""

import pytest

from src.agents.conversational_core import SLOT_ACTIVITY, ask_slot
from src.flows.state import ConversationState
from src.prompts.booking import SLOT_RESOLVER_CONTRADICCION

MENU = "¿Con cuál te animas — *buceo*, *minicurso*, *snorkel* o un *curso PADI*?"


def _estado(**campos) -> ConversationState:
    st = ConversationState(conversation_id="g1", language="es")
    for k, v in campos.items():
        setattr(st, k, v)
    return st


def test_a_quien_no_es_certificado_se_le_recomiendan_sus_opciones(monkeypatch):
    texto = ask_slot(_estado(is_certified=False), SLOT_ACTIVITY, reasking=True)
    assert MENU not in texto and "*minicurso*" in texto and "*snorkel*" in texto and "Open Water" in texto


def test_los_botones_son_los_de_un_no_certificado(monkeypatch):
    st = _estado(is_certified=False)
    ask_slot(st, SLOT_ACTIVITY)
    assert [q["value"] for q in st.quick_replies] == ["minicurso", "snorkel", "curso open water"]


def test_sin_saber_la_certificacion_sale_el_menu():
    assert MENU in ask_slot(_estado(is_certified=None), SLOT_ACTIVITY, reasking=True)


@pytest.mark.asyncio
async def test_el_resolutor_lleva_la_regla_de_contradiccion():
    from src.agents.llm_extractor import resolve_slot_answer

    visto = {}

    class _Cliente:
        class chat:
            class completions:
                @staticmethod
                async def create(**kwargs):
                    visto.update(kwargs)
                    raise RuntimeError("sin red en el test")

    await resolve_slot_answer("certification", "no, buceé hace poco", lang="es", client=_Cliente())
    assert SLOT_RESOLVER_CONTRADICCION in visto["messages"][0]["content"]
