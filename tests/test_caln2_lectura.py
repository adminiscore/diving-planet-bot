"""CALN-2 (27-oct, tanda de precios de Gadea q1/q2 contra b26392c): lectura del grupo.

(A) «I'd do the 2 dives and she the mini course»: el minicurso se nombra por su nombre del catálogo en inglés.
(B) «I told you, she wants the mini course», con la pregunta de quien no ha elegido pendiente: es su elección; la
    actividad de quien escribe sigue.
(C) La pregunta de quien no ha elegido no supone que sea quien no está certificado.
(B2) banco-lectura l04: «she'd go for the mini course. Only one day» contestando a «¿un día o varios?»: el extractor
    solo dice que habla del minicurso; la respuesta corta tomaba la duración y se volvía a preguntar qué haría ella."""

from unittest.mock import AsyncMock

import pytest

from src.agents import conversational_core as core
from src.agents.intent_detector import DetectedIntent
from src.agents.nucleo import extractor as core_extractor
from src.agents.nucleo import routing as core_routing
from src.agents.supervisor import route_message
from src.domain import activities as dom
from src.flows.state import ConversationState, Step


def _estado(**campos) -> ConversationState:
    st = ConversationState(conversation_id="caln2-lectura", language="en")
    for k, v in campos.items():
        setattr(st, k, v)
    return st


@pytest.mark.parametrize("texto, nombra", [
    ("I'd do the 2 dives and she the mini course", True),
    ("she wants the minicourse", True),
    ("ella hace el minicurso", True),
    ("I want to do the dive", False),
    ("quiero un plan de buceo", False),
])
def test_el_minicurso_por_su_nombre_del_catalogo(texto, nombra):
    assert dom.nombra_el_producto("minicourse", texto) is nombra


def test_frases_comunes_no_nombran_productos():
    assert not dom.nombra_el_producto("companion", "as a gift")
    assert not dom.nombra_el_producto("companion", "ir de compras")


def test_a_el_reparto_con_el_minicurso_en_ingles_se_acepta():
    st = _estado(detected_activity="certified_diving", detected_group_size=2)
    valido = core_extractor._reparto_valido({"certified_diving": 1, "minicourse": 1},
                                            "I'd do the 2 dives and she the mini course", st)
    assert valido == {"certified_diving": 1, "minicourse": 1}


def test_b_contesta_la_pregunta_de_quien_no_ha_elegido():
    st = _estado(detected_activity="certified_diving", detected_group_size=2, pending_undecided_qty=1,
                 core_pending_slot=core.SLOT_COMPANION_ACTIVITY, detected_group_allocation={"certified_diving": 1})
    it = DetectedIntent()
    core_extractor._poner_actividad(it, st, {"activity": "minicourse"}, "I told you, she wants the mini course")
    assert it.activity is None  # la principal no cambia
    # CALN-8 (2b): con su cantidad sabida, la elección entra ya en el reparto
    assert st.detected_group_allocation == {"certified_diving": 1, "minicourse": 1} and st.detected_group_size == 2
    assert not st.pending_undecided_qty and not st.needs_companion_activity


def test_b_sin_la_pregunta_pendiente_cambia_la_principal_como_siempre():
    st = _estado(detected_activity="certified_diving", detected_group_size=1)
    it = DetectedIntent()
    core_extractor._poner_actividad(it, st, {"activity": "minicourse"}, "actually I'd rather do the mini course")
    assert it.activity == "minicourse"


@pytest.mark.parametrize("lang, plural, esperado", [
    ("es", 1, "quien aún no ha elegido"), ("es", 2, "quienes aún no han elegido"),
    ("en", 1, "the one who hasn't chosen yet"), ("en", 2, "those who haven't chosen yet"),
])
def test_c_la_pregunta_no_supone_que_no_este_certificado(lang, plural, esperado):
    st = _estado(language=lang, pending_undecided_qty=plural)
    texto = core.ask_slot(st, core.SLOT_COMPANION_ACTIVITY)
    assert esperado in texto and "certific" not in texto.lower()


def _pareja_con_ella_sin_elegir(**campos) -> ConversationState:
    st = _estado(detected_activity="certified_diving", is_certified=True, detected_group_size=2,
                 detected_group_allocation={"certified_diving": 1}, pending_undecided_qty=1,
                 core_pending_slot=core.SLOT_COMPANION_ACTIVITY, **campos)
    st.step = Step.FREE_TEXT
    return st


@pytest.mark.parametrize("mensaje, eleccion", [
    ("Like I said, she'd go for the mini course. Only one day.", "minicourse"),
    ("Ya te dije, ella hace el minicurso. Un solo día.", "minicourse"),
    ("She can't decide between the mini course and snorkeling", None),
])
def test_b2_la_respuesta_a_un_dia_o_varios_lee_la_opcion_por_su_nombre(mensaje, eleccion):
    st = _pareja_con_ella_sin_elegir()
    core_routing._apply_short_answer(st, mensaje, ia={"jev": None, "extractor": {"actividad_preguntada": "minicourse"}})
    # CALN-8 (2b): con su cantidad sabida (1), la elección entra ya en el reparto
    assert st.detected_group_allocation == ({"certified_diving": 1, eleccion: 1} if eleccion else {"certified_diving": 1})
    assert bool(st.pending_undecided_qty) is (eleccion is None)


def test_b2_si_la_ia_lee_el_reparto_manda_el_reparto():
    mensaje = "Hacemos el paquete de 5 inmersiones y el niño el Open Water. Mi suegra va de acompañante."
    st = _pareja_con_ella_sin_elegir()
    reparto = {"certified_diving": 2, "padi_open_water": 1, "companion": 1}
    core_routing._apply_short_answer(st, mensaje, ia={"jev": None, "extractor": {"group_allocation": reparto}})
    assert st.pending_companion_activity is None


def test_b2_con_las_opciones_ya_mostradas_no_adivina_por_el_nombre():
    """g21 t3 (banco de grupos): con la duración ya sabida, «mi suegra va de acompañante» no es la opción del niño."""
    st = _pareja_con_ella_sin_elegir(detected_duration="multi_day")
    core_routing._apply_short_answer(st, "Hacemos el paquete de 5 inmersiones y el niño el Open Water. Mi suegra va de "
                                         "acompañante.")
    assert st.pending_companion_activity is None


@pytest.mark.asyncio
async def test_b2_elige_y_dice_la_duracion_en_el_mismo_mensaje(extractor_dice):
    mensaje = "Like I said, she'd go for the mini course. Only one day."
    extractor_dice({mensaje: {"actividad_preguntada": "minicourse", "dias_de_buceo": 1}})
    st = _pareja_con_ella_sin_elegir()
    await route_message(st, mensaje)
    assert st.detected_group_allocation == {"certified_diving": 1, "minicourse": 1}
    assert not st.pending_undecided_qty and st.detected_activity == "certified_diving"


@pytest.mark.asyncio
async def test_b2_si_el_extractor_tambien_la_lee_como_actividad_no_cambia_la_principal(extractor_dice):
    mensaje = "I told you, she wants the mini course. Just one day."
    extractor_dice({mensaje: {"activity": "minicourse", "actividad_preguntada": "minicourse", "dias_de_buceo": 1}})
    st = _pareja_con_ella_sin_elegir()
    await route_message(st, mensaje)
    assert st.detected_group_allocation == {"certified_diving": 1, "minicourse": 1}
    assert st.detected_activity == "certified_diving" and not st.pending_companion_activity


@pytest.fixture(autouse=True)
def _sin_llm(monkeypatch):
    from src.agents.nucleo import extraction as core_extraction

    monkeypatch.setattr(core_extraction, "resolve_slot_answer", AsyncMock(return_value={}))
    senales = AsyncMock(return_value={})
    monkeypatch.setattr(core_routing, "detect_special_signals", senales)
    monkeypatch.setattr(core_extraction, "detect_special_signals", senales)
