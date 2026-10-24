"""ex-9b paso 3: el regex deja de ser la "pista" de los campos del extractor (flag `extractor_sin_pista`, promocionado
con la ronda ex9b-3 y quitado en la limpieza ex9b junto con el camino de antes).

Antes `_understand` guardaba lo que leía `intent_detector.detect()` en los campos del extractor (actividad, origen,
certificación, grupo, nacionalidad, última inmersión) como pista: volvía si el extractor fallaba, decidía la actividad
principal de un grupo repartido (la primera lista del regex que casa: "somos 6: 2 bucean certificados, 2 hacen minicurso
y 2 snorkel" acababa en minicurso) y deducía el minicurso. Ahora:
1. la actividad principal de un grupo repartido sale del reparto del extractor (regla de CAL-F);
2. el regex no alimenta esos campos (solo la isla y el hotel del catálogo, que son de los pasos 4 y 6);
3. si el extractor falla, el dato queda sin saber y la reserva lo pregunta (decisión de Gadea);
4. la red de menciones por palabras clave ya no existe y la puerta del turno con pregunta solo mira las edades.
"""
from unittest.mock import AsyncMock

import pytest

from src.agents import conversational_core as core
from src.agents.conversational_core import SLOT_ACTIVITY, SLOT_LOCATION, ask_slot, next_missing_slot
from src.agents.extractor_turno import actividad_principal_del_reparto
from src.agents.intent_detector import DetectedIntent
from src.agents.nucleo import extraction as core_extraction
from src.agents.nucleo import extractor as core_extractor
from src.agents.nucleo import routing as core_routing
from src.agents.nucleo import slotfill_close as core_close
from src.flows.state import ConversationState, Step

GRUPO_6 = "somos 6: 2 bucean certificados, 2 hacen minicurso y 2 snorkel"
REPARTO_6 = {"certified_diving": 2, "minicourse": 2, "snorkel": 2}


@pytest.fixture
def extractor(monkeypatch):
    """Simula lo que devuelve el extractor del turno (None = la llamada falló, también su respaldo)."""

    def con(datos):
        monkeypatch.setattr(core_extractor, "datos_del_extractor", AsyncMock(return_value=datos))

    return con


def _estado(**campos) -> ConversationState:
    st = ConversationState(conversation_id="ex9b-3", language="es")
    for k, v in campos.items():
        setattr(st, k, v)
    return st


async def _entender(mensaje: str, state: ConversationState | None = None) -> ConversationState:
    state = state or _estado()
    await core._understand(state, mensaje)
    return state


# --- 0. la regla del reparto (la de CAL-F, ahora en una función) ---------------------------------------------------


def test_actividad_principal_del_reparto():
    assert actividad_principal_del_reparto({"certified_diving": 1, "minicourse": 2}) == "certified_diving"
    assert actividad_principal_del_reparto({"minicourse": 2, "snorkel": 3}) == "snorkel"
    assert actividad_principal_del_reparto({"undecided": 3}) is None
    assert actividad_principal_del_reparto({}) is None
    assert actividad_principal_del_reparto(None) is None


# --- 1. el regex no alimenta los campos del extractor -----------------------------------------------------------------


def test_la_pista_solo_trae_isla_y_hotel():
    intent = DetectedIntent(activity="certified_diving", location="island", group_size=4, is_certified=True,
                            is_colombian=False, island="isla_grande", hotel="cocoliso")
    assert core_extraction._pista_del_regex(intent) == {"island": "isla_grande", "hotel": "cocoliso"}


@pytest.mark.asyncio
async def test_no_se_deduce_el_minicurso_del_regex(extractor):
    extractor({})
    st = await _entender("nunca he buceado, es mi primera vez")
    assert st.suggested_activity is None
    assert st.detected_activity is None


@pytest.mark.asyncio
async def test_la_recomendacion_sale_de_lo_que_dice_el_extractor(extractor, monkeypatch):
    # El minicurso se sigue recomendando, pero por los hechos del extractor (CAL-C1: quiere bucear y no es certificado).
    extractor({"quiere_bucear": True, "is_certified": False})
    st = await _entender("nunca he buceado, quiero probar a bucear")
    assert next_missing_slot(st) == SLOT_ACTIVITY
    assert "te recomiendo el *minicurso*" in ask_slot(st, SLOT_ACTIVITY)


@pytest.mark.asyncio
async def test_lo_que_el_extractor_no_afirma_no_lo_pone_el_regex(extractor):
    # "hola quiero bucear con mi amigo": el regex leía buceo certificado (banco ex0, uno de sus inventos).
    extractor({"quiere_bucear": True})
    st = await _entender("hola quiero bucear con mi amigo")
    assert st.detected_activity is None
    assert st.is_certified is None


# --- 2. extractor caído: el dato queda sin saber y se pregunta --------------------------------------------------------


@pytest.mark.asyncio
async def test_caido_no_vuelve_al_regex_y_pregunta_la_actividad(extractor):
    extractor(None)
    st = await _entender("somos 4, queremos bucear certificados, salimos desde cartagena")
    assert st.detected_activity is None
    assert st.is_certified is None
    assert st.location is None and st.detected_location is None
    assert st.detected_group_size is None
    assert next_missing_slot(st) == SLOT_ACTIVITY


@pytest.mark.asyncio
async def test_caido_con_la_actividad_sabida_pregunta_el_origen(extractor):
    extractor(None)
    st = _estado(detected_activity="certified_diving", is_certified=True)
    st = await _entender("salimos desde cartagena, somos 4 y no somos colombianos", st)
    assert st.location is None
    assert st.detected_group_size is None
    assert st.is_colombian is None
    assert next_missing_slot(st) == SLOT_LOCATION


@pytest.mark.asyncio
async def test_caido_el_hotel_del_catalogo_se_conserva(extractor):
    # La isla y el hotel salen de la lista cerrada del catálogo (pasos 4 y 6): se guardan; el origen se pregunta.
    extractor(None)
    st = _estado(detected_activity="snorkel")
    st = await _entender("nos quedamos en el cocoliso", st)
    assert st.hotel or st.detected_hotel
    assert st.location is None


@pytest.mark.asyncio
async def test_caido_turno_completo_pregunta_en_vez_de_inventar(extractor, monkeypatch):
    extractor(None)
    monkeypatch.setattr(core_extraction, "fill_gaps", AsyncMock(return_value={}))
    senales = AsyncMock(return_value={})
    monkeypatch.setattr(core_routing, "detect_special_signals", senales)
    monkeypatch.setattr(core_extraction, "detect_special_signals", senales)
    monkeypatch.setattr(core, "extract_notes", AsyncMock(return_value=[]))
    monkeypatch.setattr(core_close, "_acuse_por_codigo", lambda *a, **k: "")
    st = _estado(step=Step.MAIN_MENU, history=[{"role": "user", "content": "hola"},
                                               {"role": "assistant", "content": "¡Hola! ¿En qué te ayudo?"}])
    respuesta = await core.maybe_handle_turn(st, "somos 4 buzos certificados, queremos bucear desde cartagena",
                                             routing_signals={})
    assert respuesta
    assert st.core_pending_slot == SLOT_ACTIVITY
    assert st.detected_activity is None and st.location is None and st.detected_group_size is None


# --- 3. grupo repartido: la actividad principal sale del reparto -----------------------------------------------------


@pytest.mark.asyncio
async def test_grupo_repartido_principal_del_reparto(extractor):
    # Antes, con la pista: la primera lista del regex que casa (el minicurso), aunque haya buzos certificados.
    extractor({"group_size": 6, "group_allocation": REPARTO_6})
    st = await _entender(GRUPO_6)
    assert st.detected_group_allocation == REPARTO_6
    assert st.detected_activity == "certified_diving"


@pytest.mark.asyncio
async def test_grupo_repartido_sin_buceo_certificado_la_parte_mas_grande(extractor):
    extractor({"group_size": 5, "group_allocation": {"minicourse": 2, "snorkel": 3}})
    st = await _entender("somos 5: 2 hacen el minicurso y 3 snorkel")
    assert st.detected_activity == "snorkel"


@pytest.mark.asyncio
async def test_grupo_repartido_la_actividad_elegida_manda(extractor):
    extractor({"activity": "minicourse", "group_size": 3, "group_allocation": {"minicourse": 2, "snorkel": 1}})
    st = await _entender("somos 3, queremos el minicurso 2 y uno snorkel")
    assert st.detected_activity == "minicourse"


@pytest.mark.asyncio
async def test_el_acompanante_no_le_quita_la_principal_a_quien_escribe(extractor):
    # Replay del golden (acompanante-goteo t4): "hola quiero bucear con mi amigo", "yo soy certificado", "el no es
    # certificado", "el quiere hacer snorkel" con el reparto {buceo: 1, snorkel: 1}. Antes el regex leía snorkel y la
    # principal pasaba a ser el snorkel del amigo.
    extractor({"group_allocation": {"certified_diving": 1, "snorkel": 1}})
    st = _estado(is_certified=True, detected_is_certified=True, detected_group_size=2)
    st = await _entender("el quiere hacer snorkel", st)
    assert st.detected_activity == "certified_diving"
    assert st.detected_group_allocation == {"certified_diving": 1, "snorkel": 1}


# --- 4. la puerta del turno con pregunta sobre el regex: solo las edades -----------------------------------------------


def _intent_con_actividad_y_edades() -> DetectedIntent:
    intent = DetectedIntent(activity="certified_diving", ages=[9])
    intent.detected_fields = ["activity", "ages"]
    return intent


def test_puerta_del_turno_con_pregunta_solo_mira_las_edades():
    st = _estado()
    st._answer_affirms = {"activity": False}
    intent = _intent_con_actividad_y_edades()
    assert core_extraction._question_turn_fields(intent, st) == []
    assert intent.ages == []  # las edades del regex no se pueden verificar en un turno con pregunta (como hoy)
    assert intent.activity == "certified_diving"


# --- 5. el extractor falla dos turnos seguidos: se dice y se pasa a un asesor (no se pregunta en bucle) ---------------
# El replay con el extractor caído en todos los turnos repetía "¿qué actividad?" hasta 10 veces seguidas.

@pytest.mark.asyncio
async def test_los_fallos_seguidos_se_cuentan_y_se_reinician(extractor):
    st = _estado()
    extractor(None)
    await _entender("queremos bucear el sábado", st)
    await _entender("somos 4", st)
    assert st.extractor_fallos_seguidos == 2
    extractor({"quiere_bucear": True})
    await _entender("desde cartagena", st)
    assert st.extractor_fallos_seguidos == 0


@pytest.mark.parametrize("fallos, pasa", [(1, False), (2, True)])
@pytest.mark.asyncio
async def test_al_segundo_fallo_seguido_pasa_a_un_asesor(monkeypatch, fallos, pasa):
    from src.agents import supervisor

    async def turno(conv_state, message):
        conv_state.extractor_fallos_seguidos = fallos
        return "¿Qué actividad te interesa?"

    monkeypatch.setattr("src.orchestration.graph.run_turn_via_graph", turno)
    st = _estado()
    respuesta = await supervisor.route_message(st, "somos 4")
    if pasa:
        assert "problema técnico" in respuesta and st.step == Step.ESCALATE
        assert "FALLO TÉCNICO" in st.pending_escalation_reason and "extractor" in st.pending_escalation_reason
    else:
        assert respuesta == "¿Qué actividad te interesa?" and st.pending_escalation_reason is None
