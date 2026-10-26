"""Un reparto por actividad tiene que cuadrar con el total que queda guardado (2026-09-12/14).

`supervisor.enforce_group_allocation_consistency` descarta un reparto que no suma el total (o sube el total si el reparto
suma más), contra el total que QUEDA GUARDADO (`_group_size_that_will_persist`), no contra el del turno. Motivo real:
repartos **incompletos pero visibles** ("somos 5: 3 certificados, 1 minicurso y 1 snorkel" -> {minicourse: 1,
snorkel: 1}) y totales de turno mal leídos ("4 certificados" con 7 ya sabidos).

Aquí vivía también el veto LLM de `group_allocation`: salió del camino real en ex-9, su maquinaria se borró en MEJ-1
y sus restos de `llm_extractor` (`verify_fields`, `_clean_verified_value`) en mej-1d (21-oct). Quedan la regla del
reparto y el comportamiento del regex.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.agents import supervisor
from src.agents.intent_detector import IntentDetector
from src.flows.state import ConversationState

_INCOMPLETE_MSG = "somos 5: 3 certificados, 1 minicurso y 1 snorkel"
_COMPLETE_MSG = "somos 5, 3 quieren bucear, 1 minicurso y 1 snorkel"
_REGEX_PARTIAL = {"minicourse": 1, "snorkel": 1}
_FULL_ALLOCATION = {"certified_diving": 3, "minicourse": 1, "snorkel": 1}


def _detect(msg):
    state = ConversationState(conversation_id="ga-veto-test")
    return IntentDetector().detect(msg, state), state


# -- Los flags nacen apagados ------------------------------------------------

# -- El caso real que motiva el mecanismo ------------------------------------

def test_regex_produces_an_incomplete_but_visible_allocation():
    """El fallo que se quiere cazar, tal cual, sin LLM de por medio."""
    intent, _ = _detect(_INCOMPLETE_MSG)
    assert intent.group_size == 5
    assert intent.group_allocation == _REGEX_PARTIAL
    assert sum(intent.group_allocation.values()) != intent.group_size


# -- El trigger propio -------------------------------------------------------

# -- El total puede venir de la CONVERSACION, no solo del turno ---------------
#
# Hallazgo de scripts/battery_group_allocation_gate.py (2026-09-12): el trigger
# comparaba el reparto contra `regex_intent.group_size`, el total de ESTE turno.
# En conversacion real el total casi siempre se dijo antes y vive en
# `state.detected_group_size`, asi que el veto se quedaba mudo justo en los
# casos multi-turno -- que eran los que quedaban mal en la bateria.

def _intent_con_reparto(alloc, gs=None):
    intent, _ = _detect("x")
    intent.group_allocation = alloc
    intent.group_size = gs
    return intent


# -- La invariante: el reparto debe sumar el total, VENGA DE DONDE VENGA ------
#
# Hallazgo de scripts/battery_group_allocation_gate.py (2026-09-12): la
# comprobacion "el reparto suma el total" solo la hacia el VETO, y el veto solo
# mira campos que resolvio el REGEX (la lista se calcula ANTES de la llamada al
# LLM). Un reparto producido por `fill_gaps` quedaba sin revisar: "4 con titulo
# y 2 snorkel" en un grupo de 6 se guardaba como {snorkel: 2} -- 4 personas
# fuera y la reserva mal tarificada EN SILENCIO.
#
# Se comprueba UNA vez sobre el resultado final en vez de en cada productor, asi
# que cualquier fuente futura queda cubierta sin tocar nada.

def _intent_alloc(alloc, gs=None, detected=True):
    intent, _ = _detect("x")
    intent.group_allocation = alloc
    intent.group_size = gs
    intent.detected_fields = ["group_allocation"] if detected else []
    return intent


def _state_con_total(total=None):
    s = ConversationState(conversation_id="ga-invariante")
    s.detected_group_size = total
    return s


def test_drops_an_allocation_that_does_not_add_up_to_the_turn_total():
    intent = _intent_alloc({"snorkel": 2}, gs=6)
    supervisor.enforce_group_allocation_consistency(intent, _state_con_total(), "msg")
    assert intent.group_allocation is None
    assert "group_allocation" not in intent.detected_fields


def test_drops_using_the_total_known_by_the_conversation():
    """El caso real: el total se dijo en un turno anterior."""
    intent = _intent_alloc({"snorkel": 2})
    supervisor.enforce_group_allocation_consistency(intent, _state_con_total(6), "msg")
    assert intent.group_allocation is None


def test_keeps_a_consistent_allocation():
    alloc = {"certified_diving": 4, "snorkel": 2}
    intent = _intent_alloc(alloc, gs=6)
    supervisor.enforce_group_allocation_consistency(intent, _state_con_total(), "msg")
    assert intent.group_allocation == alloc
    assert "group_allocation" in intent.detected_fields


def test_keeps_it_when_no_total_is_known_anywhere():
    """Sin total no hay invariante que comprobar: no se toca."""
    alloc = {"snorkel": 2}
    intent = _intent_alloc(alloc)
    supervisor.enforce_group_allocation_consistency(intent, _state_con_total(), "msg")
    assert intent.group_allocation == alloc


def test_a_split_that_exceeds_the_total_raises_the_total_instead_of_being_dropped():
    """El total tambien puede venir mal leido. Medido en la bateria: "3 certified
    and 3 snorkel" con el total leido como 3 descartaba un reparto CORRECTO de 6.
    Mismo criterio que `_set_group_size_from_allocation`: nunca a la baja, pero
    un reparto SI puede ampliar el total."""
    alloc = {"certified_diving": 3, "snorkel": 3}
    intent = _intent_alloc(alloc, gs=3)
    supervisor.enforce_group_allocation_consistency(intent, _state_con_total(), "msg")
    assert intent.group_allocation == alloc
    assert intent.group_size == 6
    assert "group_size" in intent.detected_fields


def test_no_allocation_is_a_no_op():
    intent = _intent_alloc(None, gs=6)
    supervisor.enforce_group_allocation_consistency(intent, _state_con_total(), "msg")
    assert intent.group_allocation is None


@pytest.mark.asyncio
async def test_invariant_runs_in_the_real_turn_path():
    """No basta con que la funcion exista: tiene que estar cableada en el turno,
    y ANTES de escribir el estado."""
    from src.agents import conversational_core as cc

    state = ConversationState(conversation_id="ga-invariante-e2e")
    state.detected_group_size = 6
    with patch.object(cc, "extract_and_verify", create=True,
                      new=AsyncMock(return_value=({"group_allocation": {"snorkel": 2}}, {}))):
        intent, _carry = await cc._understand(state, "4 con titulo y 2 snorkel")
    assert intent.group_allocation is None, (
        "un reparto que no suma el total no puede llegar al estado"
    )


# -- El total que cuenta es el que QUEDA GUARDADO, no el del turno ------------
#
# Sonda con LLM real en PRE (2026-09-14): con 7 personas ya sabidas, "4
# certificados" da group_size=4 EN EL TURNO (el regex toma la cifra de un tramo
# por el total) y `fill_gaps` devuelve {certified_diving: 4}. Contra el total del
# turno el reparto "cuadraba" y se guardaba -- pero el estado sigue en 7, porque
# el total se escribe una sola vez salvo correccion explicita. Resultado: un
# reparto de 4 personas para un grupo de 7, mal tarificado en silencio. Solo lo
# evitaba el veto de `group_size`, que depende de un flag de `.env.pre` y de que
# el LLM no degrade (con el flag apagado: 6 repartos parciales en 28 turnos).
#
# Arreglo del mecanismo, no del fraseo: los tres sitios que razonan sobre "el
# total" (guardado del estado, invariante, trigger del veto) usan la MISMA regla.

def test_the_persisted_total_ignores_a_turn_total_without_correction_cue():
    intent = _intent_alloc(None, gs=4)
    assert supervisor._group_size_that_will_persist(
        intent, _state_con_total(7), "4 certificados") == 7


def test_the_persisted_total_takes_the_turn_total_with_a_correction_cue():
    intent = _intent_alloc(None, gs=4)
    intent.overwrite = ["group_size"]  # correccion aceptada (cue), ver tarea 7b
    assert supervisor._group_size_that_will_persist(
        intent, _state_con_total(7), "en realidad somos 4") == 4


def test_the_persisted_total_takes_the_turn_total_when_nothing_was_known():
    intent = _intent_alloc(None, gs=4)
    assert supervisor._group_size_that_will_persist(
        intent, _state_con_total(), "somos 4") == 4
    assert supervisor._group_size_that_will_persist(
        _intent_alloc(None), _state_con_total(), "hola") is None


def test_drops_a_split_that_only_matches_a_misread_turn_total():
    intent = _intent_alloc({"certified_diving": 4}, gs=4)
    supervisor.enforce_group_allocation_consistency(
        intent, _state_con_total(7), "4 certificados")
    assert intent.group_allocation is None


def test_keeps_a_split_that_matches_an_explicitly_corrected_total():
    alloc = {"certified_diving": 4}
    intent = _intent_alloc(alloc, gs=4)
    intent.overwrite = ["group_size"]  # correccion aceptada (cue), ver tarea 7b
    supervisor.enforce_group_allocation_consistency(
        intent, _state_con_total(7), "en realidad somos 4, los 4 certificados")
    assert intent.group_allocation == alloc


def test_a_split_that_exceeds_the_known_total_raises_the_persisted_total():
    """La rama "amplia" tiene que llegar al ESTADO, no solo al intent: si no,
    el total escrito una sola vez se queda en 6 con un reparto de 7."""
    alloc = {"certified_diving": 4, "snorkel": 3}
    state = _state_con_total(6)
    intent = _intent_alloc(alloc)
    supervisor.enforce_group_allocation_consistency(intent, state, "4 bucean y 3 snorkel")
    supervisor._apply_detected_intent(intent, state, "4 bucean y 3 snorkel")
    assert state.detected_group_size == 7
    assert state.detected_group_allocation == alloc


def test_split_whose_turn_total_the_regex_derived_from_the_split_itself():
    """El caso `b10` de scripts/battery_group_allocation_gate.py, fallando en PRE
    con los DOS vetos encendidos (2026-09-14): con 7 sabidos, "4 con brevet, 2
    minicurso y 1 snorkel" deja al regex con {minicourse: 2, snorkel: 1} y un
    total de turno 3 DEDUCIDO de ese mismo reparto -- asi que el reparto
    "cuadraba" consigo mismo, el veto no disparaba y se guardaba un reparto de 3
    para un grupo de 7. Contra el total guardado (7) el veto dispara y, si el LLM
    no lo completa, la invariante lo descarta."""
    msg = "4 con brevet, 2 minicurso y 1 snorkel"
    state = ConversationState(conversation_id="ga-b10")
    state.detected_group_size = 7
    intent = IntentDetector().detect(msg, state)
    assert intent.group_allocation == {"minicourse": 2, "snorkel": 1}
    assert intent.group_size == 3  # el total que el regex dedujo del reparto

    supervisor.enforce_group_allocation_consistency(intent, state, msg)
    assert intent.group_allocation is None


@pytest.mark.asyncio
async def test_a_misread_turn_total_cannot_carry_a_partial_split_into_the_state():
    """El caso `m02` de la sonda, por el camino real del turno."""
    from src.agents import conversational_core as cc

    state = ConversationState(conversation_id="ga-total-mal-leido-e2e")
    state.detected_group_size = 7
    partial = {"group_allocation": {"certified_diving": 4}}
    with patch.object(cc, "extract_and_verify", create=True, new=AsyncMock(return_value=(partial, {}))):
        await cc._understand(state, "4 certificados")
    assert state.detected_group_size == 7
    assert state.detected_group_allocation is None
