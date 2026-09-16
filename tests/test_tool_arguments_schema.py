"""Los argumentos de un tool se reencajan en su esquema (hallazgo D, 2026-09-15).

Con "¿va a llover mañana en cartagena?" el LLM del router devolvia
`{"weather_conditions": true}` en vez de `{"sensitive_topic": "weather_conditions"}`:
nadie leia esa clave y la pregunta de pronostico no se escalaba. Un unico lector
(`llm_client.tool_arguments`) arregla la forma desde el esquema, para todos los tools.
"""

import json
from types import SimpleNamespace

import pytest

from src.agents import escalation
from src.llm_client import tool_arguments
from src.prompts.router import ROUTING_TOOL


def _call(args: dict):
    return SimpleNamespace(function=SimpleNamespace(arguments=json.dumps(args)))


def test_flattened_enum_flag_goes_back_to_its_field():
    assert tool_arguments(_call({"weather_conditions": True}), ROUTING_TOOL) == {
        "sensitive_topic": "weather_conditions"
    }


# Cadena EXACTA que devolvio el LLM real (sonda del 2026-09-15): rellena todos los
# campos, tambien los de enum de texto con `false`, y repite una clave.
REAL_ROUTER_ARGUMENTS = (
    '{"wants_human":false,"wants_menu_or_restart":false,"sensitive_topic":false,'
    '"adaptive_diving_topic":false,"sensitive_topic":false,"availability_question":false,'
    '"broken_link_complaint":false,"asks_for_contact_number":false,"comparing_options":false,'
    '"booking_change_topic":false,"weather_conditions":true}'
)


def test_real_router_response_with_false_placeholders_is_folded():
    call = SimpleNamespace(function=SimpleNamespace(arguments=REAL_ROUTER_ARGUMENTS))
    args = tool_arguments(call, ROUTING_TOOL)
    assert args["sensitive_topic"] == "weather_conditions"
    assert "weather_conditions" not in args


@pytest.mark.parametrize("args", [
    {"weather_conditions": "yes"},                                               # texto: no es un flag aplanado
    {"weather_conditions": False},                                               # falso: no marca nada
    {"weather_conditions": True, "sensitive_topic": "medical_questions"},        # el campo ya viene relleno
    {"made_up_key": True},                                                       # no es valor de ningun enum
])
def test_other_shapes_are_left_untouched(args):
    assert tool_arguments(_call(args), ROUTING_TOOL) == args


def test_value_shared_by_two_enums_is_not_guessed():
    tool = {"function": {"parameters": {"properties": {
        "a": {"type": "string", "enum": ["x"]}, "b": {"type": "string", "enum": ["x"]},
    }}}}
    assert tool_arguments(_call({"x": True}), tool) == {"x": True}


def test_well_formed_arguments_are_unchanged():
    args = {"sensitive_topic": "weather_conditions", "wants_human": False}
    assert tool_arguments(_call(args), ROUTING_TOOL) == args


@pytest.mark.asyncio
async def test_routing_signals_escalate_the_forecast_question_with_the_flattened_shape():
    """La respuesta exacta que dio el LLM real (batería del router, caso s04)."""
    message = SimpleNamespace(tool_calls=[SimpleNamespace(function=SimpleNamespace(arguments=REAL_ROUTER_ARGUMENTS))])

    class FakeCompletions:
        async def create(self, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    signals = await escalation.detect_routing_signals("¿va a llover mañana en cartagena?", lang="es", client=client)
    assert signals.get("sensitive_topic") == "weather_conditions"
    assert "weather_conditions" not in signals
    assert escalation.sensitive_response_for(signals["sensitive_topic"], "es") is not None


# ── Claves repetidas (2026-09-16) ───────────────────────────────────────────

def _raw(raw: str):
    return SimpleNamespace(function=SimpleNamespace(arguments=raw))


def test_repeated_enum_key_keeps_the_real_value():
    # Cadena real del LLM: detecta el pronostico y despues repite la clave en false.
    raw = '{"wants_human":false,"sensitive_topic":"weather_conditions","adaptive_diving_topic":false,"sensitive_topic":false}'
    assert tool_arguments(_raw(raw), ROUTING_TOOL)["sensitive_topic"] == "weather_conditions"


def test_repeated_boolean_key_is_last_wins_as_json():
    # En un booleano `false` es un dato, no "nada".
    assert tool_arguments(_raw('{"adaptive_diving_topic":true,"adaptive_diving_topic":false}'), ROUTING_TOOL) == {
        "adaptive_diving_topic": False
    }


def test_repeated_key_without_a_real_value_stays_as_json():
    assert tool_arguments(_raw('{"sensitive_topic":false,"sensitive_topic":false}'), ROUTING_TOOL) == {
        "sensitive_topic": False
    }
