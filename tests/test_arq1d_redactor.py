"""ARQ-1d (22-oct, flag `hechos_por_codigo`): si el mensaje solo pide intenciones que el código sabe contestar, se
escribe con los hechos del código (src/agents/redactor_hechos.py; lat-9 paso 3: el escritor del RAG, sin búsqueda); si
no, contesta el RAG de siempre."""
import asyncio
from types import SimpleNamespace

import pytest

from src.agents import conversational_core as core
from src.agents import jev_router as j
from src.agents import rag_agent, redactor_hechos
from src.agents.nucleo import extractor
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
    estado = {"texto": "El *Minicurso* cuesta 183 USD online o 204 USD sin reserva desde Cartagena, y 134 USD o 149 USD "
                      "si ya estás en las islas."}

    async def lectura(state, message):
        return {"actividad_preguntada": "minicourse"}

    async def generar(client, messages, pieza="rag_escritor"):
        hechas.append((messages, pieza))
        return SimpleNamespace(usage=SimpleNamespace(total_tokens=0),
                               choices=[SimpleNamespace(message=SimpleNamespace(content=estado["texto"]))])

    monkeypatch.setattr(extractor, "lectura_del_extractor", lectura)
    async def revisor(answer, context, lang="es"):
        return True, "ok"

    from src.agents import supervisor

    monkeypatch.setattr(rag_agent, "generar_con_respaldo", generar)
    monkeypatch.setattr(rag_agent, "_verify_grounding", revisor)
    monkeypatch.setattr(supervisor, "rag_answer", rag_agent.rag_answer)  # el escritor de verdad, con Luna simulada
    return SimpleNamespace(hechas=hechas, estado=estado)


def test_contesta_con_los_hechos_y_el_codigo_pregunta_el_origen(llamadas):
    """lat-9 paso 3: escribe el escritor del RAG (su prompt, con el catálogo), con los hechos y sin búsqueda."""
    st = _conv()
    answer = asyncio.run(redactor_hechos.responder(st, MENSAJE, st.history))
    assert answer.endswith(core.ORIGEN_TRAS_LAS_VARIANTES_ES) and core._es_pregunta_de_origen(answer)
    [(messages, pieza)] = llamadas.hechas
    assert pieza == "rag_escritor"
    assert '"183 USD"' in messages[-1]["content"] and MENSAJE in messages[-1]["content"]


def test_caln3b_si_jev_se_inclina_por_un_origen_se_confirma(llamadas):
    """CALN-3b: el extractor calla el lugar y Jev se inclina por Cartagena: los dos precios y «Entonces, ¿saldrías desde
    Cartagena?», no la pregunta abierta."""
    st = _conv()
    st._jev_lugar = {"choice": "cartagena", "confidence": 0.3}
    st._lectura_del_turno = (MENSAJE, {"actividad_preguntada": "minicourse"})
    answer = asyncio.run(redactor_hechos.responder(st, MENSAJE, st.history))
    assert answer.endswith(core._CONFIRMA_ORIGEN["cartagena"]["es"])


def test_con_origen_no_se_pregunta(llamadas):
    llamadas.estado["texto"] = "El *Minicurso* es la primera experiencia de buceo, con guía. Te dejo el precio abajo."
    st = _conv(location="cartagena")
    answer = asyncio.run(redactor_hechos.responder(st, MENSAJE, st.history))
    # CALN-3 paso 3 «A»: el texto del escritor y debajo la pieza de precios del código, sin pregunta del origen
    assert answer.startswith(llamadas.estado["texto"]) and "183 USD · 204 USD" in answer
    assert not core._es_pregunta_de_origen(answer)


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
    st._intenciones = ["incluye"]  # CALN-3 paso 2: con el precio, los candidatos (test_caln3_sin_actividad_elegida…)
    assert asyncio.run(redactor_hechos.responder(st, MENSAJE, st.history)) is None


def test_caln3_sin_actividad_elegida_los_candidatos(llamadas, monkeypatch):
    """CALN-3 paso 2 (CALN3-P01): «nunca he buceado, ¿cuánto cuesta bucear?» sin actividad elegida: el escritor recibe
    el minicurso en los dos orígenes y el código pregunta el origen detrás (antes: el RAG y la puerta sin un precio)."""
    async def lectura(state, message):
        return {"quiere_bucear": True, "is_certified": False}

    monkeypatch.setattr(extractor, "lectura_del_extractor", lectura)
    st = _conv()
    answer = asyncio.run(redactor_hechos.responder(st, MENSAJE, st.history))
    assert answer.endswith(core.ORIGEN_TRAS_LAS_VARIANTES_ES)
    [(messages, _)] = llamadas.hechas
    assert '"183 USD"' in messages[-1]["content"] and '"134 USD"' in messages[-1]["content"]


def test_caln3_con_una_actividad_en_juego_no_hay_candidatos(llamadas, monkeypatch):
    async def lectura(state, message):
        return {"quiere_bucear": True}

    monkeypatch.setattr(extractor, "lectura_del_extractor", lectura)
    st = _conv(detected_group_allocation={"snorkel": 1, "certified_diving": 1})
    st._intenciones = ["incluye"]
    assert asyncio.run(redactor_hechos.responder(st, MENSAJE, st.history)) is None


def test_la_nacionalidad_del_mensaje_pone_la_moneda(llamadas, monkeypatch):
    async def lectura(state, message):
        return {"actividad_preguntada": "minicourse", "is_colombian": True, "location": "cartagena"}

    monkeypatch.setattr(extractor, "lectura_del_extractor", lectura)
    llamadas.estado["texto"] = "El minicurso sale desde Cartagena."
    st = _conv()
    answer = asyncio.run(redactor_hechos.responder(st, MENSAJE, st.history))
    assert "655.000 COP · 727.000 COP" in answer and "USD" not in answer  # la pieza, en la moneda del mensaje
    assert "COP" in llamadas.hechas[0][0][-1]["content"] and st.is_colombian is None  # el estado no se toca


def test_otra_cosa_cuenta_como_si_salvo_un_no_seguro():
    assert j.answers_to_signals({j.PIDE_OTRA_COSA: {"noul": 0.2}})[j.PIDE_OTRA_COSA] is False
    assert j.answers_to_signals({j.PIDE_OTRA_COSA: {"noul": 0.5}})[j.PIDE_OTRA_COSA] is True


def test_la_pregunta_pendiente_no_la_ve_el_modelo(llamadas):
    """Con ella delante, Luna preguntaba el origen en vez de dar los dos enlaces (banco arq-1d, k2)."""
    st = _conv()
    asyncio.run(redactor_hechos.responder(st, MENSAJE, st.history))
    assert "pregunta_pendiente" not in llamadas.hechas[0][0][-1]["content"]


def test_si_el_escritor_no_sabe_contesta_el_rag_con_busqueda(llamadas):
    """lat-9 paso 3: ya no hay FALTA; si el escritor sin búsqueda da el «no lo tengo», contesta el RAG con la base."""
    llamadas.estado["texto"] = rag_agent.FALLBACK_ES
    st = _conv(location="cartagena")
    assert asyncio.run(redactor_hechos.responder(st, MENSAJE, st.history)) is None


def test_lat2_si_falta_un_hecho_no_se_rehace(llamadas, monkeypatch):
    """lat-2 (24-oct): ARQ-3 rehacía la respuesta en el 38 % de los turnos del redactor; ahora se queda la primera."""
    async def generar(client, messages, pieza="rag_escritor"):
        llamadas.hechas.append((messages, pieza))
        return SimpleNamespace(usage=SimpleNamespace(total_tokens=0),
                               choices=[SimpleNamespace(message=SimpleNamespace(content="Cuesta 183 USD."))])

    monkeypatch.setattr(rag_agent, "generar_con_respaldo", generar)
    st = _conv(location="cartagena")
    answer = asyncio.run(redactor_hechos.responder(st, MENSAJE, st.history))
    # CALN-3 paso 3 «A»: el importe que escribe igualmente sale; lo da la pieza
    assert "Cuesta 183 USD." not in answer and "183 USD · 204 USD" in answer
    assert len(llamadas.hechas) == 1


def test_arq1k_con_varias_actividades_en_juego_no_se_adivina():
    """G10 nº 2: buceo para el padre y snorkel para los niños; «¿qué incluye?» no nombra ninguna."""
    st = _conv(detected_activity="certified_diving", detected_group_allocation={"certified_diving": 1, "snorkel": 2})
    assert redactor_hechos._actividad(st, {}) is None
    st = _conv(detected_activity="snorkel")
    assert redactor_hechos._actividad(st, {}) == "snorkel"
    assert redactor_hechos._actividad(st, {"actividad_preguntada": "minicourse"}) == "minicourse"


def test_arq1k_los_hechos_salen_del_plan_elegido():
    from src.flows import hechos

    st = _conv(location="cartagena", selected_service="5_dives_2_days")
    [b] = hechos.hechos(st, ["precio", "incluye"], ["certified_diving"])
    assert b["precio"]["cartagena"]["online"] == "392 USD" and b.get("alojamiento")
    st.location = "island"
    [b] = hechos.hechos(st, ["precio"], ["certified_diving"])
    assert "ya en las islas" in b["precio"]["island"]["plan"]


def test_arq1n_lo_generico_se_abre_en_sus_actividades():
    st = _conv()
    assert redactor_hechos._actividades(st, {"actividad_preguntada": "padi_specialty"})[:2] == [
        "specialty_nitrox", "specialty_buoyancy"]


def test_arq1n_el_certificado_sin_bucear_hace_el_refresher():
    st = _conv(detected_activity="certified_diving", last_dive_over_2_years=True)
    assert redactor_hechos._actividad(st, {}) == "refresher"
    assert redactor_hechos._actividad(st, {"actividad_preguntada": "certified_diving"}) == "certified_diving"


def test_caln3_paso3_el_escritor_no_escribe_importes(llamadas):
    """CALN-3 paso 3 «A»: el escritor recibe la regla de no escribir importes y no se le exigen los del precio."""
    st = _conv(location="cartagena")
    asyncio.run(redactor_hechos.responder(st, MENSAJE, st.history))
    [(messages, _)] = llamadas.hechas
    from src.prompts.info import RAG_PRECIOS_POR_CODIGO

    assert RAG_PRECIOS_POR_CODIGO["es"] in messages[0]["content"]


def test_caln3_paso3_la_pieza_va_delante_de_la_pregunta_del_escritor():
    pieza = "*Precios por persona* (online · normal):\n• Minicurso: 183 USD · 204 USD"
    answer = redactor_hechos.con_la_pieza("Es tu primera inmersión. Cuesta 183 USD.\n\n¿Te paso el enlace? 🌊", pieza)
    assert answer == "Es tu primera inmersión.\n\n" + pieza + "\n\n¿Te paso el enlace? 🌊"
