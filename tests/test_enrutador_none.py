"""ex-9b (19-oct): la opción "none" en los enums del enrutador de respaldo.

DeepSeek rellena TODOS los campos del tool. Sin "none" en `sensitive_topic` y `booking_change_topic` tenía que elegir uno:
con "the discount of 10% is not showing up. what is the code?" devolvía `real_time_issues` y `cancellation` (8 de 12),
y el bot pasaba a un asesor una pregunta que se contesta (decisión de Gadea del 18-oct). "none" es la forma de decir
"nada" y, al leer, cuenta como si el campo no viniera. Las preguntas de Jev (que salen de este esquema) no cambian."""

from types import SimpleNamespace

from src.agents import jev_router as j
from src.llm_client import _is_empty_for
from src.prompts.router import ROUTING_TOOL

_PROPS = ROUTING_TOOL["function"]["parameters"]["properties"]


def test_los_dos_enums_tienen_none():
    assert _PROPS["sensitive_topic"]["enum"][-1] == "none"
    assert _PROPS["booking_change_topic"]["enum"][-1] == "none"


def test_none_es_vacio_solo_si_esta_en_el_enum():
    assert _is_empty_for(_PROPS["sensitive_topic"], "none") is True
    assert _is_empty_for({"type": "string"}, "none") is False
    assert _is_empty_for(_PROPS["sensitive_topic"], "medical_questions") is False


def test_las_preguntas_de_jev_no_cambian():
    criterios = j.routing_questions()["sensitive_topic"]["criteria"]
    assert criterios["none"] == j._NONE_SENSITIVE
    assert list(criterios) == ["medical_questions", "weather_conditions", "real_time_issues",
                               "complaints_or_emergencies", "none"]


class _Cliente:
    def __init__(self, argumentos: str):
        llamada = SimpleNamespace(function=SimpleNamespace(name="detect_routing_signals", arguments=argumentos))
        respuesta = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[llamada]))])

        async def create(**_kw):
            return respuesta

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))
