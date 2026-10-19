"""ex-9b paso 4: los regex de clase a que ya tienen un lector de IA dejan de decidir.

1. `respuesta_corta_por_ia`: la respuesta corta a la pregunta pendiente del origen, del hotel y de cuántos son la lee la
   IA (Jev `pending_answer` para el origen; el extractor para el hotel y el total), también con 12 caracteres o menos;
   los botones y una cifra sola son formato y se leen sin IA; el regex de siempre solo si la IA calla. "Voy solo" es el
   `group_size` 1 del extractor.
2. `nombre_solo_por_extractor`: si la regex ve "me llamo X", manda el `nombre` del extractor.
3. Clase A: el plan de N inmersiones del RAG lee la cifra con `dive_counts_in` (sin flag: replay igual) y los días
   cerrados los contesta el RAG con `dias_cerrados_por_rag` (con flag: sin el texto fijo, "quiero bucear el 25 de
   diciembre" no llega al RAG).
Con cada flag apagado, la conducta de hoy. (Las notas del RAG desde el estado no se hacen: el estado no tiene lo que
hace falta; ver el informe del paso 4.)
"""
from unittest.mock import AsyncMock

import pytest

from src.agents import conversational_core as core
from src.agents.conversational_core import SLOT_ACTIVITY, SLOT_HOTEL, SLOT_LOCATION, SLOT_QTY
from src.agents.intent_detector import dive_counts_in
from src.agents.nucleo import extraction as core_extraction
from src.agents.nucleo import extractor as core_extractor
from src.agents.nucleo import routing as core_routing
from src.agents.nucleo import setup as core_setup
from src.config import settings
from src.flows.catalog import policies_facts
from src.flows.state import ConversationState


def _estado(slot: str | None = None, **campos) -> ConversationState:
    st = ConversationState(conversation_id="ex9b-4", language="es")
    st.core_pending_slot = slot
    for k, v in campos.items():
        setattr(st, k, v)
    return st


def _jev(slot: str, value, confidence: float = 0.95) -> dict:
    return {"pending_answer": {"slot": slot, "value": value, "confidence": confidence}}


@pytest.fixture
def ia_on(monkeypatch):
    monkeypatch.setattr(settings, "respuesta_corta_por_ia", True)


@pytest.fixture
def ia_off(monkeypatch):
    monkeypatch.setattr(settings, "respuesta_corta_por_ia", False)


@pytest.fixture
def extractor(monkeypatch):
    """Lo que lee el extractor de este mensaje (None = falló). Devuelve el mock para ver si se le preguntó."""

    def con(datos):
        mock = AsyncMock(return_value=datos)
        monkeypatch.setattr(core_extractor, "lectura_del_extractor", mock)
        monkeypatch.setattr(core_extractor, "datos_del_extractor", AsyncMock(return_value=datos))
        return mock

    return con


async def _respuesta(state: ConversationState, message: str, signals: dict | None = None) -> bool:
    ia = await core_routing._lectura_de_la_ia(state, message, signals or {}, state.core_pending_slot)
    return core_routing._apply_short_answer(state, message, ia=ia)


# --- 1. respuestas cortas: flag apagado = hoy --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apagado_el_regex_decide_aunque_la_ia_conteste(ia_off, extractor):
    leer = extractor({"hotel": "Hilton"})
    st = _estado(SLOT_LOCATION)
    assert await _respuesta(st, "da igual", _jev(SLOT_LOCATION, "island")) is True
    assert st.location == "cartagena"  # "da igual" -> Cartagena por el regex, sin mirar a Jev
    st = _estado(SLOT_HOTEL, location="island")
    assert await _respuesta(st, "no tengo idea, el Hilton creo") is True
    assert st.hotel == "por confirmar"  # el fallo de hoy: se pierde el Hilton
    leer.assert_not_awaited()


# --- 2. encendido: lee la IA --------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_origen_delegado_lo_lee_jev(ia_on, extractor):
    leer = extractor({})
    st = _estado(SLOT_LOCATION)
    assert await _respuesta(st, "lo que tú me recomiendes", _jev(SLOT_LOCATION, "cartagena")) is True
    assert st.location == "cartagena"
    leer.assert_not_awaited()  # con la respuesta de Jev al origen no hace falta esperar al extractor


@pytest.mark.asyncio
@pytest.mark.parametrize("mensaje", ["que solo nos acompañe en la lancha, no se mete al agua",
                                     "no sé si hacer el minicurso o el snorkel"])
async def test_origen_jev_seguro_de_que_no_contesta(ia_on, extractor, mensaje):
    extractor({})
    st = _estado(SLOT_LOCATION)
    assert await _respuesta(st, mensaje, _jev(SLOT_LOCATION, None)) is False
    assert st.location is None


@pytest.mark.asyncio
async def test_origen_jev_duda_lo_dejan_al_extractor_y_a_la_red(ia_on, extractor):
    extractor({})
    st = _estado(SLOT_LOCATION)
    assert await _respuesta(st, "da igual", _jev(SLOT_LOCATION, "cartagena", confidence=0.5)) is False
    assert st.location is None  # ni el regex de "da igual": la IA ha hablado


@pytest.mark.asyncio
async def test_origen_sin_jev_y_con_extractor_no_decide_el_regex(ia_on, extractor):
    extractor({"location": "cartagena"})
    st = _estado(SLOT_LOCATION)
    assert await _respuesta(st, "cartagena") is False  # lo aplica `_understand`, como cualquier dato del extractor
    assert st.location is None


@pytest.mark.asyncio
async def test_hotel_el_del_extractor_no_se_pierde(ia_on, extractor):
    extractor({"hotel": "Hilton"})
    st = _estado(SLOT_HOTEL, location="island")
    assert await _respuesta(st, "no tengo idea, el Hilton creo") is True
    assert st.hotel == "Hilton"


@pytest.mark.asyncio
async def test_hotel_del_catalogo_da_su_isla(ia_on, extractor):
    extractor({"hotel": "el hamaquero"})
    st = _estado(SLOT_HOTEL, location="island")
    assert await _respuesta(st, "Im staying at el hamaquero") is True
    assert (st.hotel, st.island) == ("hamaquero", "isla_marina")


@pytest.mark.asyncio
@pytest.mark.parametrize("mensaje,hotel,isla", [
    ("en el Ubuntu", "ubuntu", "isla_marina"),          # el extractor no lo trae: el del catálogo que nombra el mensaje
    ("en isla grande, aún no sé el hotel", "por confirmar", "isla_grande"),  # solo la isla
])
async def test_hotel_sin_lectura_del_extractor_vale_la_lista_del_catalogo(ia_on, extractor, mensaje, hotel, isla):
    extractor({})
    st = _estado(SLOT_HOTEL, location="island")
    assert await _respuesta(st, mensaje) is True
    assert (st.hotel, st.island) == (hotel, isla)


@pytest.mark.asyncio
@pytest.mark.parametrize("mensaje", ["no sé todavía", "Veo q los 5 buceos serian por 293 pagando en el website"])
async def test_hotel_sin_hotel_en_la_respuesta_es_por_confirmar(ia_on, extractor, mensaje):
    extractor({})
    st = _estado(SLOT_HOTEL, location="island")
    assert await _respuesta(st, mensaje) is True
    assert st.hotel == "por confirmar"  # nunca el mensaje entero como hotel


@pytest.mark.asyncio
async def test_total_lo_lee_el_extractor(ia_on, extractor):
    extractor({"group_size": 1})
    st = _estado(SLOT_QTY, detected_activity="certified_diving")
    assert await _respuesta(st, "solo yo nada más") is True
    assert st.detected_group_size == 1


@pytest.mark.asyncio
async def test_total_sin_cifra_del_extractor_no_lo_decide_el_regex(ia_on, extractor):
    extractor({})
    st = _estado(SLOT_QTY, detected_activity="certified_diving")
    assert await _respuesta(st, "hace 3 años que no buceo") is False
    assert st.detected_group_size is None


@pytest.mark.asyncio
@pytest.mark.parametrize("slot,mensaje,campo,valor", [
    (SLOT_QTY, "4", "detected_group_size", 4),
    (SLOT_QTY, "dos", "detected_group_size", 2),
    (SLOT_LOCATION, "1", "location", "cartagena"),
    (SLOT_LOCATION, "isla", "location", "island"),  # el valor del botón
])
async def test_formato_sin_ia(ia_on, extractor, slot, mensaje, campo, valor):
    leer = extractor({"group_size": 9, "location": "island"})
    st = _estado(slot, detected_activity="certified_diving")
    if slot == SLOT_LOCATION:
        core.ask_slot(st, SLOT_LOCATION)  # pone los botones
        st.core_pending_slot = slot
    assert await _respuesta(st, mensaje) is True
    assert getattr(st, campo) == valor
    leer.assert_not_awaited()


# --- 3. la IA calla: el regex de siempre --------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("slot,mensaje,campo,valor", [
    (SLOT_LOCATION, "da igual", "location", "cartagena"),
    (SLOT_HOTEL, "no sé todavía", "hotel", "por confirmar"),
    (SLOT_HOTEL, "hotel las palmas", "hotel", "hotel las palmas"),
    (SLOT_QTY, "somos 4", "detected_group_size", 4),
])
async def test_la_ia_calla_decide_el_regex(ia_on, extractor, slot, mensaje, campo, valor):
    extractor(None)
    st = _estado(slot, location="island" if slot == SLOT_HOTEL else None, detected_activity="certified_diving")
    assert await core_routing._lectura_de_la_ia(st, mensaje, {}, slot) is None
    assert await _respuesta(st, mensaje) is True
    assert getattr(st, campo) == valor


@pytest.mark.asyncio
async def test_sin_el_campo_hotel_el_extractor_no_lee_hoteles(ia_on, extractor, monkeypatch):
    monkeypatch.setattr(settings, "hotel_por_extractor", False)
    extractor({})
    st = _estado(SLOT_HOTEL, location="island")
    assert await core_routing._lectura_de_la_ia(st, "hotel las palmas", {}, SLOT_HOTEL) is None


@pytest.mark.asyncio
async def test_otras_preguntas_no_cambian(ia_on, extractor):
    leer = extractor({})
    st = _estado(SLOT_ACTIVITY)
    assert await core_routing._lectura_de_la_ia(st, "da igual", _jev(SLOT_LOCATION, "cartagena"), SLOT_ACTIVITY) is None
    leer.assert_not_awaited()


# --- 4. la respuesta corta resuelta por la IA no se salta `_understand` (≤ 12 caracteres) ------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("flag,jev,lee", [(True, True, True), (False, True, False), (True, False, False)])
async def test_respuesta_corta_por_la_ia_pasa_por_el_extractor(monkeypatch, extractor, flag, jev, lee):
    monkeypatch.setattr(settings, "respuesta_corta_por_ia", flag)
    extractor(None)  # sin Jev y con el extractor caído, el regex de "da igual" (como hoy: se salta `_understand`)
    entender = AsyncMock(return_value=(None, False))
    monkeypatch.setattr(core_extraction, "_understand", entender)
    st = _estado(SLOT_LOCATION, detected_activity="certified_diving")
    st.history = [{"role": "assistant", "content": "¿Desde dónde saldrías?"}, {"role": "user", "content": "el hilton"}]
    carry = await core_routing._routing_phase(st, "el hilton" if jev else "da igual",
                                              _jev(SLOT_LOCATION, "cartagena") if jev else {}, "")
    assert carry["resolved_short"] is (flag or not jev) and st.location == ("cartagena" if flag or not jev else None)
    if not carry["resolved_short"]:
        return
    await core_extraction._extraction_phase_body(st, "el hilton" if jev else "da igual", {}, "", carry)
    assert entender.await_count == (1 if lee else 0)


# --- 5. "voy solo" -------------------------------------------------------------------------------------------------------


async def _entender(mensaje: str, **campos) -> ConversationState:
    st = _estado(None, detected_activity="certified_diving", **campos)
    await core._understand(st, mensaje)
    return st


@pytest.mark.asyncio
async def test_voy_solo_apagado_lo_decide_el_regex(ia_off, extractor):
    extractor({})
    st = await _entender("voy solo")
    assert (st.detected_group_size, st.solo_traveler_confirmed) == (1, True)


@pytest.mark.asyncio
async def test_voy_solo_encendido_lo_decide_el_extractor(ia_on, extractor):
    extractor({"group_size": 1})
    st = await _entender("voy solo")
    assert (st.detected_group_size, st.solo_traveler_confirmed) == (1, True)
    extractor({})
    st = await _entender("voy solo")  # el extractor leyó y no dice cuántos: el regex no lo pone
    assert (st.detected_group_size, st.solo_traveler_confirmed) == (None, False)
    extractor({})
    st = await _entender("soy buzo certificado, solo yo")  # "solo yo" del detector tampoco
    assert st.solo_traveler_confirmed is False


@pytest.mark.asyncio
async def test_voy_solo_con_el_extractor_caido_el_regex(ia_on, extractor):
    extractor(None)
    st = await _entender("voy solo")
    assert (st.detected_group_size, st.solo_traveler_confirmed) == (1, True)


# --- 6. el nombre ---------------------------------------------------------------------------------------------------------


@pytest.fixture
def nombre_on(monkeypatch):
    monkeypatch.setattr(settings, "nombre_por_extractor", True)
    monkeypatch.setattr(settings, "nombre_solo_por_extractor", True)


@pytest.mark.asyncio
async def test_nombre_apagado_gana_la_regex(monkeypatch, extractor):
    monkeypatch.setattr(settings, "nombre_por_extractor", True)
    monkeypatch.setattr(settings, "nombre_solo_por_extractor", False)
    leer = extractor({})
    st = _estado()
    await core_setup._nombre_del_mensaje(st, "hola, me llamo Pepe y quiero bucear")
    assert st.client_name == "Pepe"
    leer.assert_not_awaited()


@pytest.mark.asyncio
async def test_nombre_encendido_manda_el_extractor(nombre_on, extractor):
    extractor({"nombre": "Ana"})
    st = _estado()
    await core_setup._nombre_del_mensaje(st, "hola, mi nombre es ana maría")
    assert st.client_name == "Ana"
    extractor({})
    st = _estado()
    await core_setup._nombre_del_mensaje(st, "me llamo Pepe y quiero bucear")
    assert st.client_name is None  # la regex veía "Pepe"; el extractor no lee un nombre


@pytest.mark.asyncio
async def test_nombre_extractor_caido_la_regex(nombre_on, extractor):
    extractor(None)
    st = _estado()
    await core_setup._nombre_del_mensaje(st, "me llamo Pepe y quiero bucear")
    assert st.client_name == "Pepe"


@pytest.mark.asyncio
async def test_nombre_sin_la_regex_no_se_espera_al_extractor(nombre_on, extractor):
    leer = extractor({"nombre": "Rocío"})
    st = _estado()
    await core_setup._nombre_del_mensaje(st, "hola soy Rocío")
    assert st.client_name is None  # lo pone el extractor más adelante en el turno, como hoy
    leer.assert_not_awaited()


# --- 7. clase A --------------------------------------------------------------------------------------------------


def test_plan_nombrado_lee_la_cifra_con_dive_counts_in(monkeypatch):
    monkeypatch.setattr(settings, "rag_plan_nombrado", True)
    assert not hasattr(core, "_N_INMERSIONES_RE")
    isla = _estado(location="island")
    assert "1 inmersion(es)" in core._plan_nombrado(isla, "¿cuánto vale 1 inmersión desde el hotel?")  # la suelta
    assert core._plan_nombrado(_estado(location="cartagena"), "¿cuánto vale 1 inmersión?") is None  # no existe
    assert "5 inmersion(es)" in core._plan_nombrado(_estado(location="cartagena"), "y el paquete de 5?")


def test_dive_counts_in_con_tamanos():
    assert dive_counts_in("una inmersión y luego 2 buceos") == [2]  # los paquetes del catálogo
    assert dive_counts_in("una inmersión y luego 2 buceos", tamanos={1, 2}) == [1, 2]


@pytest.mark.asyncio
@pytest.mark.parametrize("flag", [False, True])
async def test_dias_cerrados(monkeypatch, flag):
    monkeypatch.setattr(settings, "dias_cerrados_por_rag", flag)
    st = _estado()
    reply = await core._availability_phase(st, "¿abren el 25 de diciembre?", {}, "")
    if flag:  # lo contesta el RAG, que lleva siempre la política
        assert reply is None
        assert "25 de diciembre" in policies_facts("es") and "December 25" in policies_facts("en")
    else:  # el texto fijo de hoy
        assert reply and "25 de diciembre" in reply
