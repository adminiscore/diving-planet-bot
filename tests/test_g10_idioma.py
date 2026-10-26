"""G-10 (decisión de Gadea, 14-oct): si el cliente escribe en otro idioma (no español ni inglés), el bot contesta en
inglés. El idioma principal del mensaje lo dice el extractor de la fase EX (promocionado; su flag `idioma_otro_en_ingles`, borrado en sim-5)."""
import asyncio

import pytest

from src.agents import conversational_core as core
from src.flows.state import ConversationState


@pytest.mark.parametrize("idioma,antes,despues", [
    ("pt", "es", "en"),   # portugués -> inglés
    ("fr", "es", "en"),
    ("es", "es", "es"),   # "Busco el seguinte… família": el extractor dice es
    ("en", "es", "es"),   # el inglés lo decide el camino de siempre (no se toca aquí)
    (None, "es", "es"),   # sin dato, el idioma de siempre
])
def test_otro_idioma_en_ingles(monkeypatch, idioma, antes, despues):
    st = ConversationState(conversation_id="g10", language=antes)
    asyncio.run(core._otro_idioma_en_ingles(st, {"idioma": idioma} if idioma else {}, "Olá, quero fazer mergulho"))
    assert st.language == despues


def test_con_la_conversacion_en_marcha_una_palabra_de_otro_idioma_no_la_cambia():
    """lat-deuda (26-oct): «Y para transferência tiene descuento?» en el turno 9 de una conversación en español pasaba al
    inglés. El idioma lo fija la apertura; después, solo una petición del cliente."""
    st = ConversationState(conversation_id="g10", language="es")
    st.history = [{"role": "user", "content": "Buzos certificados"}, {"role": "assistant", "content": "¡Hola!"},
                  {"role": "user", "content": "Y para transferência tiene descuento? Tengo cuenta local"}]
    asyncio.run(core._otro_idioma_en_ingles(st, {"idioma": "pt"}, st.history[-1]["content"]))
    assert st.language == "es"


def test_primer_turno_mira_la_extraccion_ya_lanzada_sin_consumirla(monkeypatch):
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
def test_la_regla_de_no_adivinar_sustituye_a_la_de_no_suponer(monkeypatch, lang):
    """18-oct (decisión de Gadea: no adivinar nada que el cliente no haya dicho): con `rag_no_adivina` el prompt lleva
    la regla ampliada (origen, nacionalidad, certificación, cuántos, fechas…) y no la vieja, que solo cubría el
    servicio; las dos a la vez se contradirían en el alcance. Desde lat-9 paso 1 va en dos partes: la de no atribuir
    (reglas de cualquier escritor) y la de preguntar lo que falta (solo del RAG)."""
    from src.agents.rag_agent import build_system_prompt
    from src.prompts import info

    prompt = build_system_prompt(lang)
    es = lang == "es"
    assert (info.ESCRITOR_NO_ADIVINA_ES if es else info.ESCRITOR_NO_ADIVINA_EN) in prompt
    assert (info.RAG_PREGUNTA_LO_QUE_FALTA_ES if es else info.RAG_PREGUNTA_LO_QUE_FALTA_EN) in prompt
    assert (info.RAG_NO_SUPONE_ES if es else info.RAG_NO_SUPONE_EN) not in prompt


def test_una_o_dos_palabras_no_cambian_el_idioma(monkeypatch):
    """Ronda flujo1-B2: "Frances" (contesta "¿sois colombianos?") pasaba la conversación a inglés."""
    st = ConversationState(conversation_id="g10", language="es")
    asyncio.run(core._otro_idioma_en_ingles(st, {"idioma": "fr"}, "Frances"))
    assert st.language == "es"


def test_una_respuesta_corta_no_es_un_nombre(monkeypatch):
    st = ConversationState(conversation_id="g10", language="es")
    st.core_pending_slot = "nationality"
    core._nombre_del_extractor(st, {"nombre": "Frances"}, "Frances")
    assert st.client_name is None

