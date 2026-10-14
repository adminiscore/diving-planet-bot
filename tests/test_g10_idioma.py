"""G-10 (decisión de Gadea, 14-oct): si el cliente escribe en otro idioma (no español ni inglés), el bot contesta en
inglés. El idioma principal del mensaje lo dice el extractor de la fase EX (flag `idioma_otro_en_ingles`)."""
import asyncio

import pytest

from src.agents import conversational_core as core
from src.config import settings
from src.flows.state import ConversationState


@pytest.mark.parametrize("idioma,antes,despues", [
    ("pt", "es", "en"),   # portugués -> inglés
    ("fr", "es", "en"),
    ("es", "es", "es"),   # "Busco el seguinte… família": el extractor dice es
    ("en", "es", "es"),   # el inglés lo decide el camino de siempre (no se toca aquí)
    (None, "es", "es"),   # sin dato, el idioma de siempre
])
def test_otro_idioma_en_ingles(monkeypatch, idioma, antes, despues):
    monkeypatch.setattr(settings, "idioma_otro_en_ingles", True)
    st = ConversationState(conversation_id="g10", language=antes)
    asyncio.run(core._otro_idioma_en_ingles(st, {"idioma": idioma} if idioma else {}, "Olá, quero fazer mergulho"))
    assert st.language == despues


def test_apagado_no_cambia(monkeypatch):
    monkeypatch.setattr(settings, "idioma_otro_en_ingles", False)
    st = ConversationState(conversation_id="g10", language="es")
    asyncio.run(core._otro_idioma_en_ingles(st, {"idioma": "pt"}, "Olá, quero fazer mergulho"))
    assert st.language == "es"


def test_primer_turno_mira_la_extraccion_ya_lanzada_sin_consumirla(monkeypatch):
    monkeypatch.setattr(settings, "idioma_otro_en_ingles", True)

    async def caso():
        st = ConversationState(conversation_id="g10", language="es")

        async def extraccion():
            return {"idioma": "pt"}

        st._extraccion_adelantada = asyncio.ensure_future(extraccion())
        await core._otro_idioma_en_ingles(st, message="Olá, quero fazer mergulho")
        assert st.language == "en" and st.detected_language == "en"
        assert st._extraccion_adelantada is not None  # _understand la vuelve a esperar
        assert (await st._extraccion_adelantada) == {"idioma": "pt"}

    asyncio.run(caso())


def test_politicas_enteras_para_el_rag():
    """EX-RAG-1: todas las políticas, en el idioma del turno (la de equipaje, que el RAG no recuperaba, incluida)."""
    import json
    from pathlib import Path

    from src.flows.catalog import policies_facts

    n = len(json.loads(Path("data/knowledge_base/policies.json").read_text(encoding="utf-8"))["policies"])
    es, en = policies_facts("es"), policies_facts("en")
    assert es.count("\n- ") == n and en.count("\n- ") == n
    assert "mochila" in es and "backpack" in en


@pytest.mark.parametrize("lang", ["es", "en"])
def test_regla_de_no_suponer_en_el_prompt_del_rag(monkeypatch, lang):
    """EX-RAG-2: con el flag, el prompt del RAG lleva la regla de no atribuir al cliente un servicio que no dijo."""
    from src.agents.rag_agent import build_system_prompt
    from src.prompts.info import RAG_NO_SUPONE_EN, RAG_NO_SUPONE_ES

    regla = RAG_NO_SUPONE_ES if lang == "es" else RAG_NO_SUPONE_EN
    monkeypatch.setattr(settings, "rag_no_supone_reserva", False)
    assert regla not in build_system_prompt(lang)
    monkeypatch.setattr(settings, "rag_no_supone_reserva", True)
    assert regla in build_system_prompt(lang)


def test_una_o_dos_palabras_no_cambian_el_idioma(monkeypatch):
    """Ronda flujo1-B2: "Frances" (contesta "¿sois colombianos?") pasaba la conversación a inglés."""
    monkeypatch.setattr(settings, "idioma_otro_en_ingles", True)
    st = ConversationState(conversation_id="g10", language="es")
    asyncio.run(core._otro_idioma_en_ingles(st, {"idioma": "fr"}, "Frances"))
    assert st.language == "es"


def test_una_respuesta_corta_no_es_un_nombre(monkeypatch):
    monkeypatch.setattr(settings, "nombre_por_extractor", True)
    st = ConversationState(conversation_id="g10", language="es")
    st.core_pending_slot = "nationality"
    core._nombre_del_extractor(st, {"nombre": "Frances"}, "Frances")
    assert st.client_name is None

