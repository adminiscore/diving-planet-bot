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

def test_both_flags_default_to_false():
    assert settings.llm_group_allocation_veto_shadow_mode is False
    assert settings.llm_group_allocation_veto_cutover is False


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
    assert "group_allocation" not in supervisor._eligible_veto_fields(_INCOMPLETE_MSG, intent)
    with patch.object(supervisor.settings, "llm_group_allocation_veto_shadow_mode", True):
        assert "group_allocation" in supervisor._eligible_veto_fields(_INCOMPLETE_MSG, intent)


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
    intent, state = _detect(_INCOMPLETE_MSG)
    with patch.object(supervisor.settings, "llm_group_allocation_veto_shadow_mode", True), \
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
