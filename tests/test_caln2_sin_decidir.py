"""CALN-2 (27-oct, Álvaro (3)): quien viene sin elegir queda SIN DECIDIR, no con la actividad que supone la red de
señales (decisión «no asumir»: se le recomienda y elige el cliente). Banco de grupos g02, g26 y g28."""

from unittest.mock import AsyncMock, patch

import pytest

from src.agents import conversational_core as core
from src.agents.nucleo import extraction as core_extraction
from src.agents.nucleo import routing as core_routing
from src.agents.supervisor import route_message
from src.flows.state import ConversationState


@pytest.fixture(autouse=True)
def _sin_resolver(monkeypatch):
    monkeypatch.setattr(core_extraction, "resolve_slot_answer", AsyncMock(return_value={}))


def _estado() -> ConversationState:
    st = ConversationState(conversation_id="caln2-sin-decidir")
    st.language = "es"
    return st


async def _turno(st, mensaje, senales):
    falsa = AsyncMock(return_value=senales)
    with patch.object(core_routing, "detect_special_signals", new=falsa), \
            patch.object(core_extraction, "detect_special_signals", new=falsa):
        return await route_message(st, mensaje)


@pytest.mark.asyncio
async def test_no_ha_buceado_nunca_no_es_minicurso(extractor_dice, monkeypatch):
    """g02: «mi novia que no ha buceado nunca» no es minicurso (el mensaje no lo nombra): queda sin decidir. CALN-8
    (28-oct): con el extractor sin reparto, la cuenta la hace el lector del grupo (antes, la red de señales)."""
    mensaje = "Quiero bucear, soy certificado. Voy con mi novia que no ha buceado nunca"
    extractor_dice({mensaje: {"activity": "certified_diving", "is_certified": True, "otro_sin_certificar": True}})
    _con_el_lector(monkeypatch, [_persona("cliente", True, "Quiero bucear, soy certificado"),
                                 _persona("novia", False, "Voy con mi novia que no ha buceado nunca")])
    st = _estado()
    await _turno(st, mensaje, {})
    assert "minicourse" not in (st.detected_group_allocation or {})
    assert st.pending_undecided_qty == 1 and st.detected_group_size == 2


@pytest.mark.asyncio
async def test_la_amiga_que_no_sabe_no_es_buzo(extractor_dice, monkeypatch):
    """g28: la amiga que no sabe qué hacer no hereda la actividad de quien escribe. CALN-8 (28-oct): con el extractor sin
    reparto, la cuenta la hace el lector del grupo (antes, la red de señales)."""
    mensaje = "Quiero bucear, soy buzo certificado. Viene también mi amiga, pero no sabe qué quiere hacer"
    extractor_dice({mensaje: {"activity": "certified_diving", "is_certified": True}})
    _con_el_lector(monkeypatch, [_persona("cliente", True, "Quiero bucear, soy buzo certificado"),
                                 _persona("amiga", None, "Viene también mi amiga, pero no sabe qué quiere hacer")])
    # El extractor no dice nada de la amiga: el lector se usa porque Jev está seguro de que se suma alguien.
    monkeypatch.setattr("src.agents.supervisor.detect_routing_signals",
                        AsyncMock(return_value={"companion_joins": 0.95}))
    st = _estado()
    await _turno(st, mensaje, {})
    assert (st.detected_group_allocation or {}).get("certified_diving", 0) <= 1
    assert st.pending_undecided_qty == 1 and st.detected_group_size == 2


@pytest.mark.asyncio
async def test_el_marido_que_se_suma_a_quien_ya_eligio(extractor_dice, monkeypatch):
    """g19 (medida de CALN-8, 28-oct): «quiero hacer el minicurso» y luego «mi marido es certificado, quiere bucear».
    El extractor no dice nada del grupo y el lector nombra solo al marido; quien escribe ya eligió, así que van 2."""
    extractor_dice({"quiero hacer el minicurso": {"activity": "minicourse"},
                    "mi marido es certificado, quiere bucear": {}})
    marido = {**_persona("marido", True, "mi marido es certificado, quiere bucear"), "actividad": "certified_diving"}
    _con_el_lector(monkeypatch, [marido])
    st = _estado()
    await _turno(st, "quiero hacer el minicurso", {})
    assert st.detected_activity == "minicourse" and not st.detected_group_size
    monkeypatch.setattr("src.agents.supervisor.detect_routing_signals",
                        AsyncMock(return_value={"companion_joins": 0.97}))
    await _turno(st, "mi marido es certificado, quiere bucear", {})
    assert st.detected_group_size == 2
    assert st.detected_group_allocation == {"minicourse": 1, "certified_diving": 1}
    assert st.detected_activity == "minicourse"


@pytest.mark.asyncio
async def test_vienen_unos_amigos_sin_elegir_se_pregunta_que_haran_y_cuantos(extractor_dice, monkeypatch):
    """g26 (CALN-8, 28-oct): «Vienen también unos amigos, no sé qué querrán hacer». No se sabe cuántos ni qué harán: se
    pregunta qué harán y después cuántos; el grupo queda con quien escribe y ellos. Antes, sin la red de señales y sin
    el 1 que el lector inventaba a «unos amigos», se seguía con el origen como si no viniera nadie."""
    mensaje = "Quiero bucear, soy buzo certificado. Vienen también unos amigos, no sé qué querrán hacer"
    extractor_dice({mensaje: {"activity": "certified_diving", "is_certified": True}, "un día": {}, "snorkel": {},
                    "3": {}})
    _con_el_lector(monkeypatch, [_persona("cliente", True, "Quiero bucear, soy buzo certificado"),
                                 {**_persona("amigos", None, "Vienen también unos amigos, no sé qué querrán hacer"),
                                  "cantidad": None}])
    monkeypatch.setattr("src.agents.supervisor.detect_routing_signals",
                        AsyncMock(return_value={"companion_joins": 0.96}))
    st = _estado()
    await _turno(st, mensaje, {})
    assert st.core_pending_slot == core.SLOT_COMPANION_ACTIVITY and not st.detected_group_size
    monkeypatch.setattr("src.agents.supervisor.detect_routing_signals", AsyncMock(return_value={}))
    await _turno(st, "single_day", {})
    assert st.core_pending_slot == core.SLOT_COMPANION_ACTIVITY
    assert "snorkel" in [b["value"] for b in st.quick_replies]
    await _turno(st, "snorkel", {})
    assert st.core_pending_slot == core.SLOT_COMPANION_QTY
    await _turno(st, "3", {})
    assert st.detected_group_allocation == {"certified_diving": 1, "snorkel": 3}
    assert st.detected_group_size == 4 and st.detected_activity == "certified_diving"


@pytest.mark.asyncio
async def test_queremos_el_minicurso_y_luego_somos_3(extractor_dice, monkeypatch):
    """g10 (2.ª medida de CALN-8, 28-oct): «Queremos hacer el minicurso» y luego «Somos 3». El lector lee «Somos 3» como
    quien escribe con 2 más; lo que eligió antes no es solo suyo («queremos»): nadie queda sin decidir."""
    extractor_dice({"Queremos hacer el minicurso": {"activity": "minicourse"}, "Somos 3": {"group_size": 3}})
    _con_el_lector(monkeypatch, [{**_persona("cliente", None, "Somos 3"), "cantidad": 3}])
    st = _estado()
    await _turno(st, "Queremos hacer el minicurso", {})
    await _turno(st, "Somos 3", {})
    assert st.detected_group_size == 3 and not st.pending_undecided_qty
    assert (st.detected_group_allocation or {"minicourse": 3}) == {"minicourse": 3}


def _persona(quien, certificado, cita):
    return {"quien": quien, "cantidad": 1, "certificado": certificado, "actividad": None, "edades": [], "cita": cita}


def _con_el_lector(monkeypatch, personas):
    """El lector del grupo encendido, con su lectura simulada (validada como la de verdad)."""
    from src.agents import lector_grupo
    from src.config import settings

    async def _leer(mensaje, **_kw):
        return {**lector_grupo.validar({"personas": personas}, mensaje), "segundos": 0.0}

    monkeypatch.setattr(settings, "lector_grupo", True)
    monkeypatch.setattr(lector_grupo, "leer_grupo", _leer)


@pytest.mark.asyncio
async def test_unos_amigos_sin_numero_no_se_cuentan(extractor_dice):
    """g26: sin decidir y sin poder contarlos: nadie se suma con la actividad de quien escribe."""
    mensaje = "Quiero bucear, soy buzo certificado. Vienen también unos amigos, no sé qué querrán hacer"
    extractor_dice({mensaje: {"activity": "certified_diving", "is_certified": True}})
    st = _estado()
    await _turno(st, mensaje, {"companion_activity": "certified_diving", "mentions_other_person": True})
    assert (st.detected_group_allocation or {}).get("certified_diving", 0) <= 1
    assert not st.pending_undecided_qty


@pytest.mark.asyncio
async def test_si_el_extractor_ve_al_grupo_manda_el(extractor_dice):
    """Con el reparto del extractor en este turno, la red de señales no decide (el reparto ya resuelto)."""
    mensaje = "Somos 2 buzos certificados y queremos bucear"
    extractor_dice({mensaje: {"activity": "certified_diving", "is_certified": True, "group_size": 2}})
    st = _estado()
    await _turno(st, mensaje, {"companion_activity": "certified_diving", "mentions_other_person": True,
                               "companion_is_singular": True})
    assert st.detected_group_size == 2 and not st.pending_undecided_qty


def _pareja(**campos) -> ConversationState:
    st = _estado()
    st.detected_activity, st.detected_group_size, st.is_certified = "certified_diving", 2, True
    st.detected_group_allocation = {"certified_diving": 1}
    st.pending_undecided_qty, st.sin_decidir_certificados = 1, True
    st.core_pending_slot = core.SLOT_COMPANION_ACTIVITY
    for k, v in campos.items():
        setattr(st, k, v)
    return st


@pytest.mark.parametrize("campos, pregunta", [
    ({}, True),
    ({"sin_decidir_certificados": None}, False),  # no se sabe si está certificado: las opciones
    ({"detected_activity": "snorkel", "detected_group_allocation": {"snorkel": 1}}, False),  # quien escribe no bucea
])
def test_si_quien_falta_esta_certificado_se_pregunta_si_tambien_bucea(campos, pregunta):
    """CALN-8 (pareja Advanced del golden, decisión de Gadea #2475): una pregunta de sí o no en vez de «¿un día o
    varios?» y las opciones."""
    st = _pareja(**campos)
    texto = core.ask_slot(st, core.SLOT_COMPANION_ACTIVITY)
    assert ("también va a bucear" in texto) is pregunta
    if pregunta:
        assert [b["value"] for b in st.quick_replies] == ["certified_diving", core.OTRA_COSA]


@pytest.mark.parametrize("respuesta", ["certified_diving", "sí", "si, los dos"])
def test_si_tambien_bucea_entran_los_dos(respuesta):
    st = _pareja()
    assert core_routing._apply_short_answer(st, respuesta)
    assert st.detected_group_allocation == {"certified_diving": 2} and st.detected_group_size == 2
    assert not st.pending_undecided_qty and not st.needs_companion_activity


@pytest.mark.parametrize("respuesta", [core.OTRA_COSA, "no"])
def test_si_no_bucea_se_le_recomiendan_las_opciones(respuesta):
    st = _pareja()
    assert core_routing._apply_short_answer(st, respuesta)
    assert st.pending_undecided_qty == 1 and st.sin_decidir_certificados is None
    assert "un solo día" in core.ask_slot(st, core.SLOT_COMPANION_ACTIVITY)


@pytest.mark.asyncio
async def test_la_pareja_de_buzos_se_pregunta_y_bucean_los_dos(extractor_dice, monkeypatch):
    """La pareja de buzos que quiere bucear, leída como quien escribe con buceo y otra persona certificada sin elegir:
    se pregunta si también bucea y, con el sí, el buceo es para los dos. Frase nuestra."""
    mensaje = "Hola, somos una pareja de buzos Advanced y queremos hacer unas inmersiones en Cartagena"
    extractor_dice({mensaje: {"activity": "certified_diving", "is_certified": True, "group_size": 2}, "sí": {}})
    _con_el_lector(monkeypatch, [{**_persona("cliente", True, mensaje), "cantidad": 2}])
    st = _estado()
    await _turno(st, mensaje, {})
    assert st.core_pending_slot == core.SLOT_COMPANION_ACTIVITY and st.sin_decidir_certificados is True
    assert [b["value"] for b in st.quick_replies] == ["certified_diving", core.OTRA_COSA]
    await _turno(st, "sí", {})
    assert st.detected_group_allocation == {"certified_diving": 2} and not st.pending_undecided_qty


def test_a_quien_falta_y_esta_certificado_no_se_le_ofrecen_cursos_de_principiante():
    """Sparring s29c (pareja de Barú, los dos Advanced): el menú de quien no ha elegido no lleva el minicurso ni el curso
    Open Water si se sabe que está certificado."""
    st = _pareja(sin_decidir_certificados=True, detected_duration="multi_day")
    opciones = core._companion_activity_options(st)
    assert opciones[0] == "certified_diving"
    assert "minicourse" not in opciones and "padi_open_water" not in opciones
    st.sin_decidir_certificados = None  # sin saberlo, siguen todas
    assert {"minicourse", "padi_open_water"} <= set(core._companion_activity_options(st))
