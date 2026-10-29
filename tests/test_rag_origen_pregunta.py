"""`rag_origen_pregunta` (punto 3: el ORIGEN del cliente en los precios; promocionado, sin interruptor desde mej-1d).

6-oct: un aviso en el contexto del RAG, medido y quitado (o repreguntaba o volvía a suponer Cartagena).
7-oct, opción C (decisión de Álvaro): lo hace el CÓDIGO. Se fija:
1. cuándo se pregunta el origen en vez de cotizar: la respuesta del RAG lleva un importe, el cliente pide un precio
   (o repregunta tras la pregunta del origen sin contestarla: "¿y en pesos?"), el origen no consta y el cliente no ha
   nombrado Cartagena ni las islas; no si el precio es del hotel, ni si la respuesta no cotiza (la MONEDA: ronda
   origen-c-B, 7-oct), ni con el flag apagado;
2. en la reserva: la pregunta del origen ocupa el turno (en lugar de la cotización, con sus botones) y se guarda la
   del precio;
3. cuando el cliente dice el origen, se contesta la pregunta del precio que quedó pendiente;
4. si una respuesta del RAG ya pregunta el origen, la reserva no repite la suya.
"""
from unittest.mock import AsyncMock

import pytest

from src.agents import conversational_core as core
from src.agents import supervisor
from src.agents.nucleo import extraction as core_extraction
from src.agents.nucleo import routing as core_routing
from src.agents.nucleo import slotfill_close as core_close
from src.agents.supervisor import route_message
from src.flows.state import ConversationState, Step

PREGUNTA_RAG = "El precio depende de desde dónde salgan. ¿Saldrían desde Cartagena o ya están en las islas?"
COTIZA = "El minicurso cuesta 655.000 COP (o 178 USD)."


def _estado(location=None, historial=None, pendiente=None) -> ConversationState:
    s = ConversationState(conversation_id="origen", language="es")
    s.pregunta_precio_pendiente = pendiente
    s.step = Step.FREE_TEXT
    s.location = location
    s.history = historial or []
    return s


# CALN-3 paso 4 (2) (29-oct): la puerta del origen se quitó; si la respuesta cotiza, sus importes los pone la pieza de
# `cotizar` (`_con_la_pieza`), y la pregunta del origen va detrás salvo que el cliente lo haya dado.
@pytest.mark.parametrize("location,historial,mensaje,pregunta", [
    (None, [], "¿cuánto cuesta el minicurso?", True),
    (None, [], "Cuál es el costo para colombianos?", True),
    (None, [], "how much is the 5 dive package?", True),
    ("cartagena", [], "¿cuánto cuesta el minicurso?", False),             # el origen consta
    (None, [], "salimos desde Cartagena, ¿cuánto cuesta?", False),        # lo dice en el mensaje
    (None, [{"role": "user", "content": "we will book our hotel on the island"}],
     "how much is the refresher?", False),                                       # lo dio a entender antes
    (None, [{"role": "assistant", "content": "saliendo desde Cartagena o desde las propias islas"}],
     "¿cuánto cuesta?", True),                                                   # lo que dice el BOT no cuenta
])
def test_cuando_se_pregunta_el_origen_tras_la_pieza(monkeypatch, location, historial, mensaje, pregunta):
    salida = core._con_la_pieza(_estado(location, historial), mensaje, COTIZA)
    assert "*Precios por persona*" in salida and "RESPUESTA" not in salida
    assert core._es_pregunta_de_origen(salida) is pregunta


@pytest.mark.parametrize("respuesta,pieza", [
    # ronda origen-c-B (7-oct): dice "precio" pero pregunta la MONEDA; la respuesta no cotiza -> va tal cual
    ("Los precios en dólares son para internacionales y en pesos (COP) para colombianos.", False),
    # ronda origen-c-B: «Gracias - y en pesos?» tras la pregunta del origen: el RAG cotizaba Cartagena
    ("El paquete de 5 inmersiones cuesta 1.429.000 COP.", True),
    ("It costs USD 178 per person.", True),
])
def test_la_pieza_mira_si_la_respuesta_cotiza(monkeypatch, respuesta, pieza):
    assert (core._con_la_pieza(_estado(), "Gracias - y en pesos?", respuesta) is not None) is pieza


@pytest.mark.parametrize("slot,respuesta,va_sola", [
    (core.SLOT_LOCATION, PREGUNTA_RAG, True),
    (core.SLOT_LOCATION, "Where would you be departing from: Cartagena or the islands?", True),
    (core.SLOT_LOCATION, "¿Desde dónde prefieren salir ustedes? Así te paso el link correcto.", True),
    (core.SLOT_LOCATION, "¿me confirmas si saldrían desde Cartagena o si ya están en las islas?", True),
    (core.SLOT_QTY, PREGUNTA_RAG, False),
    (core.SLOT_LOCATION, "El minicurso cuesta 655.000 COP desde Cartagena.", False),
])
def test_la_respuesta_que_ya_pregunta_el_origen_va_sola(monkeypatch, slot, respuesta, va_sola):
    state = _estado()
    state.core_pending_slot = slot
    assert core._answer_asks_the_origin(state, respuesta) is va_sola


@pytest.fixture
def conversacion(monkeypatch, extractor_dice):
    """La reserva entera, sin red: señales vacías, extractores apagados y un RAG falso que apunta sus preguntas.

    ex-9b paso 3: el extractor del turno, simulado con lo que dicen los mensajes de reserva (sin él, en los tests falla
    y, a los dos fallos seguidos, se pasa a un asesor)."""
    extractor_dice({"queremos bucear, somos certificados":
                    {"quiere_bucear": True, "is_certified": True, "activity": "certified_diving"},
                    "desde cartagena": {"location": "cartagena"}})
    _senales = AsyncMock(return_value={})
    monkeypatch.setattr(core_routing, "detect_special_signals", _senales)
    monkeypatch.setattr(core_extraction, "detect_special_signals", _senales)
    monkeypatch.setattr(core_extraction, "resolve_slot_answer", AsyncMock(return_value={}))
    monkeypatch.setattr(core, "extract_notes", AsyncMock(return_value=[]))
    monkeypatch.setattr(core_close, "_acuse_por_codigo", lambda *a, **k: "")
    monkeypatch.setattr(core, "lanzar_rag_adelantado", lambda *a, **k: None)  # rag-5: sin respuesta adelantada

    async def _senales(message, **_k):
        return {}

    monkeypatch.setattr(supervisor, "detect_routing_signals", _senales)
    preguntas = []

    async def _rag(message, **kwargs):
        preguntas.append({"message": message, "extra_context": kwargs.get("extra_context") or ""})
        return f"RESPUESTA_RAG: {COTIZA}"

    monkeypatch.setattr(supervisor, "rag_answer", _rag)
    return preguntas


async def test_pide_precio_sin_origen_se_pregunta_y_luego_se_contesta(monkeypatch, conversacion):
    st = ConversationState(conversation_id="origen-c", language="es")
    await route_message(st, "queremos bucear, somos certificados")
    resp = await route_message(st, "¿cuánto cuesta?")
    # CALN-3 paso 4 (1): la cotización del RAG no sale; van los precios de la pieza, de los dos orígenes, y la pregunta
    assert "RESPUESTA_RAG" not in resp and "*Desde Cartagena*" in resp
    assert resp.endswith(core.ORIGEN_TRAS_LAS_VARIANTES_ES)
    assert st.core_pending_slot == core.SLOT_LOCATION and st.quick_replies  # con sus botones
    assert st.pregunta_precio_pendiente == "¿cuánto cuesta?"
    assert resp.count("¿") == 1  # una sola pregunta, sin la de la reserva detrás

    resp = await route_message(st, "desde cartagena")
    # se contesta la pregunta del precio que quedó pendiente (CALN-3 paso 4 (1): con los importes de la pieza)
    assert resp.startswith("*Precios por persona*") and "630.000" in resp
    assert conversacion[-1]["message"] == "¿cuánto cuesta?"
    assert st.pregunta_precio_pendiente is None
    assert st.location == "cartagena" or st.detected_location == "cartagena"


async def test_y_en_pesos_tras_la_pregunta_del_origen_tampoco_cotiza(monkeypatch, conversacion):
    """Ronda origen-c-B (7-oct): "Gracias - y en pesos?" no lleva palabras de precio y el RAG cotizaba Cartagena."""
    st = ConversationState(conversation_id="origen-pesos", language="es")
    await route_message(st, "queremos bucear, somos certificados")
    await route_message(st, "¿cuánto cuesta?")
    resp = await route_message(st, "Gracias - y en pesos?")
    assert conversacion[-1]["message"] == "Gracias - y en pesos?"  # el RAG contestó (y cotizaba)...
    assert "RESPUESTA_RAG" not in resp and resp.endswith(core.ORIGEN_TRAS_LAS_VARIANTES_ES)  # ...pieza y pregunta
    assert st.pregunta_precio_pendiente  # sigue pendiente: se contesta cuando diga el origen


# s4-31 (8-oct, flag `origen_conserva_respuesta`): la puerta del origen ya no tira la respuesta entera. Ronda
# 2026-10-08-luna-visible: 6 de 33 fallos del RAG eran de perder lo que no era el precio.
MITO = ("¡Qué bueno que quieras hacer el curso! Para colombianos no hay un precio especial: el precio es el mismo para "
        "todos, solo cambia la moneda (pagas en pesos). El curso cuesta 2.450.000 COP online saliendo desde Cartagena. "
        "¿Quieres que te pase el link?")


def test_conserva_lo_que_no_es_precio_y_pregunta_el_origen(monkeypatch):
    salida = core._con_la_pieza(_estado(), "Cuál es el costo para colombianos?", MITO)
    assert "no hay un precio especial" in salida and "solo cambia la moneda" in salida  # lo que no es precio, queda
    assert "El curso cuesta 2.450.000" not in salida and "link" not in salida            # su importe y su pregunta, fuera
    assert "*Desde Cartagena*" in salida and "2.450.000" in salida                       # el importe, de la pieza
    assert salida.endswith(core.ORIGEN_TRAS_LAS_VARIANTES_ES) and core._es_pregunta_de_origen(salida)


@pytest.mark.parametrize("respuesta", ["Cuesta 655.000 COP. ¿Te lo reservo?", "El minicurso: 183 USD online."])
def test_si_solo_habia_precio_queda_la_pieza_y_la_pregunta(monkeypatch, respuesta):
    salida = core._con_la_pieza(_estado(), "¿cuánto cuesta?", respuesta)
    assert salida.startswith("*Precios por persona*") and salida.endswith(core.ORIGEN_TRAS_LAS_VARIANTES_ES)


def test_tambien_quita_el_link(monkeypatch):
    """Escalón 0 en PRE (8-oct): se dejaba el link de Cartagena mientras se preguntaba el origen. Lo que incluye
    («Incluye teoría online y 4 inmersiones») ya no se quita: la pieza dice el precio de cada origen."""
    respuesta = ("¡Claro que sí! Incluye teoría online y 4 inmersiones. 693 USD.\nSon 2 días y hay que dormir una noche en "
                 "las islas; el alojamiento no está incluido. Reserva aquí: https://book.divingplanet.org/book/basic-course/4")
    salida = core._con_la_pieza(_estado(), "¿cuánto cuesta el curso?", respuesta)
    assert "book.divingplanet.org" not in salida and "el alojamiento no está incluido" in salida


def test_si_el_escritor_da_los_dos_origenes_la_pieza_los_da_igual():
    """27-oct (decisión «origen-y-precio»: sin el origen, dos precios y pregunta)."""
    st = _estado()
    st.detected_activity = "certified_diving"
    salida = core._con_la_pieza(st, "¿cuánto cuesta?", "Desde Cartagena: 178 USD por persona. Ya en las islas: 124 USD.")
    assert "*Desde Cartagena*" in salida and "*Ya en las Islas del Rosario*" in salida
    assert salida.endswith(core.ORIGEN_TRAS_LAS_VARIANTES_ES)
