"""gen-5 (20-oct, flag `idioma_unico_de_apertura`): el idioma del primer mensaje se decide UNA vez en el router del
grafo, con la cadena de la reserva (extractor, palabras vacías, LLM, pistas y G-10), y todas las rutas lo heredan."""
import asyncio

import pytest

from src.agents import supervisor
from src.agents.nucleo import setup
from src.config import settings
from src.flows.state import ConversationState, Step
from src.orchestration import graph


def _extraccion(idioma: str):
    async def _datos():
        return {"idioma": idioma}

    return asyncio.ensure_future(_datos())


@pytest.fixture
def router_sin_llamadas(monkeypatch):
    """El router sin red: señales vacías, sin RAG adelantado y una extracción adelantada que dice el idioma pedido."""
    monkeypatch.setattr(settings, "idioma_del_extractor", True)

    async def _senales(*_a, **_k):
        return {}

    monkeypatch.setattr(supervisor, "detect_routing_signals", _senales)
    monkeypatch.setattr("src.agents.conversational_core.lanzar_rag_adelantado", lambda *_a: None)
    idioma = {"valor": "pt"}

    def _lanzar(conv, _message):
        conv._extraccion_adelantada = _extraccion(idioma["valor"])

    monkeypatch.setattr("src.agents.conversational_core.lanzar_extraccion_adelantada", _lanzar)
    return idioma


async def test_idioma_de_apertura_aplica_g10(monkeypatch):
    monkeypatch.setattr(settings, "idioma_del_extractor", True)
    st = ConversationState(conversation_id="gen5")
    st._extraccion_adelantada = _extraccion("pt")
    await setup.idioma_de_apertura(st, "Estou grávida de três meses, posso fazer o batismo de mergulho?")
    assert st.language == "en" and st.detected_language == "en"


@pytest.mark.parametrize("mensaje,idioma,esperado", [
    ("Estou grávida de três meses, posso fazer o batismo de mergulho?", "pt", "en"),
    ("I had ear surgery three months ago, can I still dive with you?", "en", "en"),
    ("Tengo asma desde niña, ¿puedo hacer el minicurso?", "es", "es"),
])
async def test_con_el_flag_el_router_fija_el_idioma_para_todas_las_rutas(
        monkeypatch, router_sin_llamadas, mensaje, idioma, esperado):
    monkeypatch.setattr(settings, "idioma_unico_de_apertura", True)
    router_sin_llamadas["valor"] = idioma
    conv = ConversationState(conversation_id="gen5")
    await graph._router_node({"conv_state": conv, "message": mensaje})
    assert conv.language == esperado and conv.detected_language == esperado
    # Lo sensible (`_reply_language`) y el contacto o "¿eres un bot?" (miran `detected_language`) lo heredan.
    assert supervisor._reply_language(conv, mensaje) == esperado


async def test_apagado_el_router_no_toca_el_idioma(monkeypatch, router_sin_llamadas):
    monkeypatch.setattr(settings, "idioma_unico_de_apertura", False)
    conv = ConversationState(conversation_id="gen5")
    await graph._router_node({"conv_state": conv, "message": "Estou grávida de três meses, posso mergulhar?"})
    assert conv.detected_language is None


async def test_fuera_de_la_apertura_el_router_no_vuelve_a_decidir(monkeypatch, router_sin_llamadas):
    monkeypatch.setattr(settings, "idioma_unico_de_apertura", True)
    conv = ConversationState(conversation_id="gen5", language="es")
    conv.detected_language = "es"
    conv.step = Step.FREE_TEXT
    await graph._router_node({"conv_state": conv, "message": "Obrigado, e quanto custa o snorkel para as crianças?"})
    assert conv.language == "es"


async def test_la_reserva_no_vuelve_a_decidir_lo_que_decidio_el_router(monkeypatch):
    monkeypatch.setattr(settings, "idioma_unico_de_apertura", True)
    llamadas = []

    async def _contar(state, message):
        llamadas.append(message)

    async def _sin_notas(*_a, **_k):
        return None

    monkeypatch.setattr(setup, "idioma_de_apertura", _contar)
    monkeypatch.setattr(setup, "_maybe_capture_notes", _sin_notas)
    conv = ConversationState(conversation_id="gen5", language="en")
    conv.detected_language = "en"
    await setup._setup_phase(conv, "Olá, somos quatro e queremos fazer snorkel", {})
    assert llamadas == [] and conv.language == "en" and conv.step == Step.FREE_TEXT

    monkeypatch.setattr(settings, "idioma_unico_de_apertura", False)
    conv = ConversationState(conversation_id="gen5")
    await setup._setup_phase(conv, "Olá, somos quatro e queremos fazer snorkel", {})
    assert llamadas == ["Olá, somos quatro e queremos fazer snorkel"]
