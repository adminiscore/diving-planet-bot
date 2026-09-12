"""Tests del veto LLM de `group_allocation` (docs/robustness/progress-log.md,
2026-09-12; justificacion en el comentario de `config.py`).

Motivo real: tras arreglar que un reparto incompleto redujera ademas el
`group_size` declarado (2026-09-10), quedan repartos **incompletos pero
visibles** -- el total esta bien y el reparto no suma el total:

    "somos 5: 3 certificados, 1 minicurso y 1 snorkel"
    -> group_size=5 (correcto), allocation={minicourse:1, snorkel:1}

porque "N certificados" sin verbo no matchea `activity_kw`. El regex vuelve a
CONTESTAR CON CONFIANZA y equivocarse, que es exactamente lo que este
mecanismo caza (y lo que `fill_gaps` no puede: su regla es no tocar un campo
ya resuelto).

NO confundir la justificacion con el 91% de `group_allocation` en el
eval-set: el unico caso que falla alli
(`hist-followup-must-not-rederive-resolved-group-allocation`) es una
alucinacion de `fill_gaps` leyendo el historial, y el veto ni se dispararia
sobre el -- solo actua sobre campos que el REGEX resolvio ESTE turno.

Dos particularidades frente al resto de campos del mecanismo:

1. Tiene `should_verify` PROPIO (`_group_allocation_should_verify`): solo
   dispara si el reparto no suma el `group_size` conocido. Es la leccion de
   `activity` (trigger generico -> 89%->73%, revertido) aplicada de entrada.
2. Es el unico campo que es un **dict** y no un escalar. `verify_fields` y
   `_clean_verified_value` ya lo contemplaban, pero no habia test que lo
   fijara: el resto del mecanismo se diseno pensando en escalares.

Ambos flags en `False` por defecto en todas partes: shadow-mode primero,
nunca cutover sin datos.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.agents import supervisor
from src.agents.intent_detector import IntentDetector
from src.agents.llm_extractor import _clean_verified_value, verify_fields
from src.config import settings
from src.flows.state import ConversationState

_INCOMPLETE_MSG = "somos 5: 3 certificados, 1 minicurso y 1 snorkel"
_COMPLETE_MSG = "somos 5, 3 quieren bucear, 1 minicurso y 1 snorkel"
_REGEX_PARTIAL = {"minicourse": 1, "snorkel": 1}
_FULL_ALLOCATION = {"certified_diving": 3, "minicourse": 1, "snorkel": 1}


def _detect(msg):
    state = ConversationState(conversation_id="ga-veto-test")
    return IntentDetector().detect(msg, state), state


def _client_returning(payload):
    """Cliente OpenAI de mentira que devuelve `payload` como tool_call."""
    async def _create(**kwargs):
        call = SimpleNamespace(function=SimpleNamespace(
            name="extract_fields", arguments=json.dumps(payload)))
        return SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(tool_calls=[call]))])

    client = AsyncMock()
    client.chat.completions.create = _create
    return client


# -- Los flags nacen apagados ------------------------------------------------

def test_cutover_is_on_by_default_and_shadow_is_not():
    """Unico campo del mecanismo que nace en cutover. Se activo con datos
    medidos ANTES (bateria de conversacion: 6/10 repartos correctos frente a
    3/10, 0 parciales, 0 alucinaciones), no a ver que tal."""
    assert settings.llm_group_allocation_veto_shadow_mode is False
    assert settings.llm_group_allocation_veto_cutover is True


# -- El caso real que motiva el mecanismo ------------------------------------

def test_regex_produces_an_incomplete_but_visible_allocation():
    """El fallo que se quiere cazar, tal cual, sin LLM de por medio."""
    intent, _ = _detect(_INCOMPLETE_MSG)
    assert intent.group_size == 5
    assert intent.group_allocation == _REGEX_PARTIAL
    assert sum(intent.group_allocation.values()) != intent.group_size


# -- El trigger propio -------------------------------------------------------

def test_should_verify_fires_when_allocation_does_not_add_up():
    intent, _ = _detect(_INCOMPLETE_MSG)
    assert supervisor._group_allocation_should_verify(_INCOMPLETE_MSG, intent) is True


def test_should_verify_stays_quiet_when_allocation_adds_up():
    """Coste cero en los repartos que ya cuadran -- y, sobre todo, no se mete
    al LLM a opinar sobre algo que el regex resolvio bien."""
    intent, _ = _detect(_COMPLETE_MSG)
    assert sum(intent.group_allocation.values()) == intent.group_size
    assert supervisor._group_allocation_should_verify(_COMPLETE_MSG, intent) is False


def test_should_verify_abstains_without_a_group_size_to_compare_against():
    intent, _ = _detect(_INCOMPLETE_MSG)
    intent.group_size = None
    assert supervisor._group_allocation_should_verify(_INCOMPLETE_MSG, intent) is False


def test_should_verify_abstains_without_allocation():
    intent, _ = _detect(_INCOMPLETE_MSG)
    intent.group_allocation = None
    assert supervisor._group_allocation_should_verify(_INCOMPLETE_MSG, intent) is False


def test_eligible_only_when_a_flag_is_on():
    intent, _ = _detect(_INCOMPLETE_MSG)
    with patch.object(supervisor.settings, "llm_group_allocation_veto_cutover", False):
        assert "group_allocation" not in supervisor._eligible_veto_fields(
            _INCOMPLETE_MSG, intent)
        with patch.object(supervisor.settings,
                          "llm_group_allocation_veto_shadow_mode", True):
            assert "group_allocation" in supervisor._eligible_veto_fields(
                _INCOMPLETE_MSG, intent)


# -- Es un DICT, no un escalar -----------------------------------------------

def test_clean_verified_value_keeps_a_dict_and_strips_schema_nulls():
    """El schema estricto devuelve todas las claves, con null en las no usadas
    (igual que en `fill_gaps`)."""
    raw = {"certified_diving": 3, "minicourse": 1, "snorkel": 1,
           "padi_open_water": None, "padi_advanced": 0}
    assert _clean_verified_value("group_allocation", raw) == _FULL_ALLOCATION


def test_clean_verified_value_discards_an_all_null_dict():
    assert _clean_verified_value("group_allocation", {"snorkel": None}) is None


@pytest.mark.asyncio
async def test_verify_fields_reports_a_dict_disagreement():
    """La comparacion `!=` de `verify_fields` tiene que funcionar sobre dicts,
    no solo sobre escalares."""
    out = await verify_fields(
        ["group_allocation"], _INCOMPLETE_MSG,
        {"group_allocation": _REGEX_PARTIAL}, lang="es",
        client=_client_returning({"group_allocation": _FULL_ALLOCATION}),
    )
    assert out == {"group_allocation": _FULL_ALLOCATION}


@pytest.mark.asyncio
async def test_verify_fields_reports_nothing_when_the_dict_matches():
    out = await verify_fields(
        ["group_allocation"], _COMPLETE_MSG,
        {"group_allocation": dict(_FULL_ALLOCATION)}, lang="es",
        client=_client_returning({"group_allocation": dict(_FULL_ALLOCATION)}),
    )
    assert out == {}


# -- Shadow no aplica, cutover si --------------------------------------------

@pytest.mark.asyncio
async def test_shadow_mode_measures_without_applying():
    """`cutover` va a True por defecto desde 2026-09-12, asi que aqui hay que
    apagarlo explicitamente para probar el shadow."""
    intent, state = _detect(_INCOMPLETE_MSG)
    with patch.object(supervisor.settings, "llm_group_allocation_veto_shadow_mode", True), \
         patch.object(supervisor.settings, "llm_group_allocation_veto_cutover", False), \
         patch.object(supervisor, "verify_fields",
                      new=AsyncMock(return_value={"group_allocation": _FULL_ALLOCATION})):
        await supervisor._maybe_veto_resolved_fields_via_llm(_INCOMPLETE_MSG, intent, state)
    assert intent.group_allocation == _REGEX_PARTIAL


@pytest.mark.asyncio
async def test_cutover_applies_the_complete_allocation():
    intent, state = _detect(_INCOMPLETE_MSG)
    with patch.object(supervisor.settings, "llm_group_allocation_veto_cutover", True), \
         patch.object(supervisor, "verify_fields",
                      new=AsyncMock(return_value={"group_allocation": _FULL_ALLOCATION})):
        await supervisor._maybe_veto_resolved_fields_via_llm(_INCOMPLETE_MSG, intent, state)
    assert intent.group_allocation == _FULL_ALLOCATION
    assert sum(intent.group_allocation.values()) == intent.group_size


@pytest.mark.asyncio
async def test_llm_failure_degrades_to_the_regex_value():
    intent, state = _detect(_INCOMPLETE_MSG)
    with patch.object(supervisor.settings, "llm_group_allocation_veto_cutover", True), \
         patch.object(supervisor, "verify_fields",
                      new=AsyncMock(side_effect=RuntimeError("boom"))):
        await supervisor._maybe_veto_resolved_fields_via_llm(_INCOMPLETE_MSG, intent, state)
    assert intent.group_allocation == _REGEX_PARTIAL


# -- El prompt agrupado tiene que saber renderizar el campo -------------------

@pytest.mark.parametrize("lang", ["es", "en"])
def test_verification_prompt_renders_group_allocation(lang):
    """`fields_verification_system_prompt` hace `rules[f]`: sin entrada propia
    en `_FIELD_VERIFICATION_RULES_*` reventaria con KeyError en cuanto el
    campo entrase en un lote."""
    from src.prompts.booking import fields_verification_system_prompt

    prompt = fields_verification_system_prompt(["group_size", "group_allocation"], lang)
    assert "group_allocation" in prompt
    assert "certified_diving" in prompt


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


def test_trigger_uses_the_total_known_by_the_conversation():
    state = ConversationState(conversation_id="ga-multi-turno")
    state.detected_group_size = 6
    intent = _intent_con_reparto({"snorkel": 2})  # reparto a medias, sin total en el turno
    assert supervisor._group_allocation_should_verify("4 con titulo y 2 snorkel",
                                                      intent, state) is True


def test_trigger_still_abstains_with_no_total_anywhere():
    state = ConversationState(conversation_id="ga-sin-total")
    intent = _intent_con_reparto({"snorkel": 2})
    assert supervisor._group_allocation_should_verify("...", intent, state) is False
    assert supervisor._group_allocation_should_verify("...", intent, None) is False


def test_trigger_prefers_this_turns_total_over_the_conversations():
    """Si el turno declara un total, manda ese: es el dato mas fresco."""
    state = ConversationState(conversation_id="ga-turno-manda")
    state.detected_group_size = 99
    intent = _intent_con_reparto({"certified_diving": 2, "snorkel": 1}, gs=3)
    assert supervisor._group_allocation_should_verify("...", intent, state) is False


def test_trigger_stays_quiet_when_the_conversations_total_already_matches():
    state = ConversationState(conversation_id="ga-cuadra")
    state.detected_group_size = 3
    intent = _intent_con_reparto({"certified_diving": 2, "snorkel": 1})
    assert supervisor._group_allocation_should_verify("...", intent, state) is False


def test_should_verify_is_still_callable_with_two_arguments():
    """`state` es opcional a proposito: hay llamadas de 2 argumentos vivas."""
    intent = _intent_con_reparto({"snorkel": 2}, gs=5)
    assert supervisor._group_allocation_should_verify("...", intent) is True


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
    with patch.object(cc, "extract_and_verify",
                      new=AsyncMock(return_value=({"group_allocation": {"snorkel": 2}}, {}))), \
         patch.object(cc, "fill_gaps",
                      new=AsyncMock(return_value={"group_allocation": {"snorkel": 2}})):
        intent, _carry = await cc._understand(state, "4 con titulo y 2 snorkel")
    assert intent.group_allocation is None, (
        "un reparto que no suma el total no puede llegar al estado"
    )
