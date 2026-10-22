"""ARQ-1d (22-oct, flag `hechos_por_codigo`): si el mensaje solo pide intenciones que el código sabe contestar, Luna
redacta con los hechos del código (src/agents/redactor_hechos.py); si no, contesta el RAG de siempre."""
import asyncio
from types import SimpleNamespace

import pytest

from src.agents import conversational_core as core
from src.agents import jev_router as j
from src.agents import rag_agent, redactor_hechos
from src.agents.nucleo import extractor
from src.config import settings
from src.flows.state import ConversationState

MENSAJE = "¿Cuánto cuesta el minicurso?"


def _conv(lang="es", **campos) -> ConversationState:
    st = ConversationState(conversation_id="arq1d", language=lang)
    st.history = [{"role": "user", "content": MENSAJE}]
    st._intenciones = ["precio"]
    st._otra_cosa = False
    for k, v in campos.items():
        setattr(st, k, v)
    return st


@pytest.fixture
def llamadas(monkeypatch):
    """El extractor lee el minicurso de este mensaje y Luna contesta con `texto`; se guardan los mensajes que recibe."""
    hechas: list = []
    estado = {"texto": "El *Minicurso* cuesta 183 USD desde Cartagena y 134 USD si ya estás en las islas."}

    async def lectura(state, message):
        return {"actividad_preguntada": "minicourse"}

    async def generar(client, messages, pieza="rag_escritor"):
        hechas.append((messages, pieza))
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=estado["texto"]))])

    monkeypatch.setattr(extractor, "lectura_del_extractor", lectura)
    monkeypatch.setattr(rag_agent, "generar_con_respaldo", generar)
    monkeypatch.setattr(redactor_hechos, "trace_openai", lambda c: c)
    return SimpleNamespace(hechas=hechas, estado=estado)


def test_contesta_con_los_hechos_y_el_codigo_pregunta_el_origen(llamadas):
    st = _conv()
    answer = asyncio.run(redactor_hechos.responder(st, MENSAJE, st.history))
    assert answer.endswith(core.ORIGEN_TRAS_LAS_VARIANTES_ES) and core._es_pregunta_de_origen(answer)
    [(messages, pieza)] = llamadas.hechas
    assert pieza == "redactor_hechos"
    assert "SOLO con los HECHOS" in messages[0]["content"] and "Catálogo" not in messages[0]["content"]
    assert '"183 USD"' in messages[-1]["content"] and messages[-1]["content"].endswith(MENSAJE)
    assert sum(1 for m in messages if MENSAJE in m["content"]) == 1  # el mensaje no va dos veces


def test_con_origen_no_se_pregunta(llamadas):
    llamadas.estado["texto"] = "El *Minicurso* desde Cartagena cuesta 183 USD por persona."
    st = _conv(location="cartagena")
    assert asyncio.run(redactor_hechos.responder(st, MENSAJE, st.history)) == llamadas.estado["texto"]


@pytest.mark.parametrize("campos", [{"_otra_cosa": None}, {"_otra_cosa": True}, {"_intenciones": []}])
def test_si_jev_no_esta_seguro_contesta_el_rag(llamadas, campos):
    st = _conv(**campos)
    assert asyncio.run(redactor_hechos.responder(st, MENSAJE, st.history)) is None
    assert llamadas.hechas == []


def test_la_pregunta_guardada_de_otro_turno_va_al_rag(llamadas):
    """El precio pendiente que se contesta al decir el origen: las intenciones de Jev son las de «desde Cartagena»."""
    st = _conv()
    st.history.append({"role": "user", "content": "desde Cartagena"})
    assert asyncio.run(redactor_hechos.responder(st, MENSAJE, st.history)) is None


def test_un_importe_que_no_esta_en_los_hechos_va_al_rag(llamadas):
    llamadas.estado["texto"] = "El minicurso cuesta 199 USD."
    st = _conv(location="cartagena")
    assert asyncio.run(redactor_hechos.responder(st, MENSAJE, st.history)) is None


def test_sin_actividad_va_al_rag(llamadas, monkeypatch):
    async def lectura(state, message):
        return {}

    monkeypatch.setattr(extractor, "lectura_del_extractor", lectura)
    st = _conv()
    assert asyncio.run(redactor_hechos.responder(st, MENSAJE, st.history)) is None


def test_la_nacionalidad_del_mensaje_pone_la_moneda(llamadas, monkeypatch):
    async def lectura(state, message):
        return {"actividad_preguntada": "minicourse", "is_colombian": True, "location": "cartagena"}

    monkeypatch.setattr(extractor, "lectura_del_extractor", lectura)
    llamadas.estado["texto"] = "El minicurso desde Cartagena cuesta 655.000 COP."
    st = _conv()
    assert asyncio.run(redactor_hechos.responder(st, MENSAJE, st.history)) == llamadas.estado["texto"]
    assert "COP" in llamadas.hechas[0][0][-1]["content"] and st.is_colombian is None  # el estado no se toca


def test_con_el_flag_apagado_ni_se_mira(llamadas, monkeypatch):
    monkeypatch.setattr(settings, "hechos_por_codigo", False)
    st = _conv()
    assert asyncio.run(core._con_hechos(st, MENSAJE, st.history)) is None
    assert llamadas.hechas == []


def test_otra_cosa_cuenta_como_si_salvo_un_no_seguro():
    assert j.answers_to_signals({j.PIDE_OTRA_COSA: {"noul": 0.2}})[j.PIDE_OTRA_COSA] is False
    assert j.answers_to_signals({j.PIDE_OTRA_COSA: {"noul": 0.5}})[j.PIDE_OTRA_COSA] is True


def test_la_pregunta_pendiente_no_la_ve_el_modelo(llamadas):
    """Con ella delante, Luna preguntaba el origen en vez de dar los dos enlaces (banco arq-1d, k2)."""
    st = _conv()
    asyncio.run(redactor_hechos.responder(st, MENSAJE, st.history))
    assert "pregunta_pendiente" not in llamadas.hechas[0][0][-1]["content"]


@pytest.mark.parametrize("intenciones, tarjeta", [(["precio", "incluye", "edad"], False), (["edad"], True)])
def test_la_tarjeta_de_edades_no_se_come_las_otras_preguntas(monkeypatch, intenciones, tarjeta):
    """ARQ-1e: con más intenciones que la edad, el turno lo contesta el redactor de hechos."""
    from src.agents.rutas.info import _maybe_answer_age_eligibility

    monkeypatch.setattr(settings, "hechos_por_codigo", True)
    st = _conv(_intenciones=intenciones)
    respuesta = _maybe_answer_age_eligibility("Mi hijo tiene 12 años, ¿cuánto cuesta el minicurso y desde qué edad "
                                              "se puede?", st)
    assert (respuesta is not None) is tarjeta


def test_si_los_hechos_no_contestan_lo_que_pregunta_contesta_el_rag(llamadas):
    """Jev no marcó una intención (v3: «what time do we meet» a 0,72): el redactor dice FALTA y contesta el RAG."""
    llamadas.estado["texto"] = "FALTA"
    st = _conv(location="cartagena")
    assert asyncio.run(redactor_hechos.responder(st, MENSAJE, st.history)) is None


def test_falta_en_medio_de_la_respuesta_tampoco_llega_al_cliente(llamadas):
    """Banco D, v2: «…Incluye: … / FALTA / ¿Y para cuántas personas…?» habría llegado tal cual."""
    llamadas.estado["texto"] = "El snorkel cuesta 45 USD.\n\nFALTA\n\n¿Para cuántas personas?"
    st = _conv(location="island")
    assert asyncio.run(redactor_hechos.responder(st, MENSAJE, st.history)) is None
    # Core B2: al final de una frase.
    llamadas.estado["texto"] = "El snorkel cuesta 45 USD. No tengo el precio del refresher. FALTA"
    assert asyncio.run(redactor_hechos.responder(st, MENSAJE, st.history)) is None
