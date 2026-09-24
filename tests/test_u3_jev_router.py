"""U3 (u3-1, paso 1): las señales del router con Jev, detrás de flag y con respaldo.

Lo que se fija aquí:
1. con el flag APAGADO (por defecto) no se llama a Jev: la conducta es la de siempre;
2. con el flag encendido, si Jev responde, esa es la respuesta y no se llama al LLM;
3. si Jev falla (sin clave, error, tiempo máximo, respuesta rara), se usa el router LLM;
4. las respuestas de Jev se traducen al MISMO dict que devuelve el router LLM;
5. la configuración es la que ganó en l2-4 (`scripts/jev_router_eval.py --v2`).
"""

import json

import httpx
import pytest

from src.agents import escalation, jev_router
from src.config import Settings, settings


class _FakeLLM:
    """Cliente OpenAI de mentira: cuenta las llamadas y no marca ninguna señal."""

    def __init__(self):
        self.calls = 0
        outer = self

        class _Completions:
            async def create(self, **_kw):
                outer.calls += 1

                class _Msg:
                    tool_calls = None

                class _Choice:
                    message = _Msg()

                class _Resp:
                    choices = [_Choice()]

                return _Resp()

        class _Chat:
            completions = _Completions()

        self.chat = _Chat()


@pytest.fixture
def llm(monkeypatch):
    fake = _FakeLLM()
    monkeypatch.setattr(escalation, "AsyncOpenAI", lambda **_kw: object())
    monkeypatch.setattr(escalation, "trace_openai", lambda _c: fake)
    return fake


@pytest.fixture
def facts(monkeypatch):
    seen = {}
    import src.observability as obs

    monkeypatch.setattr(obs, "note_turn", lambda **kw: seen.update(kw))
    return seen


def test_el_flag_nace_apagado():
    assert Settings().jev_router_enabled is False


async def test_flag_apagado_no_llama_a_jev(monkeypatch, llm):
    async def _no(*_a, **_k):
        raise AssertionError("con el flag apagado no se llama a Jev")

    monkeypatch.setattr(settings, "jev_router_enabled", False)
    monkeypatch.setattr(jev_router, "detect_routing_signals_jev", _no)
    await escalation.detect_routing_signals("quiero hablar con un asesor")
    assert llm.calls == 1


async def test_con_flag_manda_jev_y_no_se_llama_al_llm(monkeypatch, llm, facts):
    async def _jev(message, *, lang="es"):
        return {"wants_human": True}

    monkeypatch.setattr(settings, "jev_router_enabled", True)
    monkeypatch.setattr(jev_router, "detect_routing_signals_jev", _jev)
    got = await escalation.detect_routing_signals("quiero hablar con un asesor")
    assert got == {"wants_human": True}
    assert llm.calls == 0
    assert facts["router"] == "jev"


async def test_si_jev_falla_se_usa_el_router_llm(monkeypatch, llm, facts):
    async def _falla(message, *, lang="es"):
        return None

    monkeypatch.setattr(settings, "jev_router_enabled", True)
    monkeypatch.setattr(jev_router, "detect_routing_signals_jev", _falla)
    await escalation.detect_routing_signals("quiero hablar con un asesor")
    assert llm.calls == 1
    assert facts["router"] == "llm_fallback"


def test_traduccion_de_respuestas_al_dict_del_router():
    answers = {
        "wants_human": {"type": "noul", "noul": 0.9},
        "wants_menu_or_restart": {"type": "noul", "noul": 0.49},
        "adaptive_diving_topic": {"type": "noul", "noul": 0.1},
        "availability_question": {"type": "noul", "noul": 0.5},
        "broken_link_complaint": {"type": "noul", "noul": 0.0},
        "asks_for_contact_number": {"type": "noul", "noul": 0.0},
        "sensitive_topic": {"type": "choice", "choice": "none"},
        "booking_change_topic": {"type": "choice", "choice": "reschedule"},
        "comparing": {"type": "noul", "noul": 0.8},
        "opt_minicourse": {"type": "noul", "noul": 0.9},
        "opt_snorkel": {"type": "noul", "noul": 0.7},
        "opt_padi_course": {"type": "noul", "noul": 0.2},
    }
    assert jev_router.answers_to_signals(answers) == {
        "wants_human": True,
        "availability_question": True,
        "booking_change_topic": "reschedule",
        "comparing_options": {"comparing": True, "options": ["minicourse", "snorkel"]},
    }


def test_sin_comparacion_no_hay_opciones():
    answers = {"comparing": {"type": "noul", "noul": 0.2}, "opt_snorkel": {"type": "noul", "noul": 0.9}}
    assert jev_router.answers_to_signals(answers) == {}


def test_la_configuracion_es_la_evaluada_en_l2_4():
    from scripts import jev_router_eval

    assert jev_router.routing_questions() == jev_router_eval._questions(v2=True)
    assert jev_router.THRESHOLD == 0.5


def _mock_http(monkeypatch, handler):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(jev_router, "_client", client)
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-or-test")


async def test_llamada_correcta_devuelve_las_senales(monkeypatch):
    enviado = {}

    def handler(request: httpx.Request):
        enviado.update(json.loads(request.content))
        return httpx.Response(200, json={"answers": {"wants_human": {"type": "noul", "noul": 0.95}}})

    _mock_http(monkeypatch, handler)
    got = await jev_router.detect_routing_signals_jev("me puede atender una persona?")
    assert got == {"wants_human": True}
    assert enviado["model"] == settings.jev_model
    assert "me puede atender una persona?" in enviado["state"]
    assert set(enviado["questions"]) == set(jev_router.routing_questions())


@pytest.mark.parametrize(
    "handler",
    [
        lambda r: httpx.Response(500, text="error"),
        lambda r: httpx.Response(200, text="no es json"),
        lambda r: httpx.Response(200, json={"sin": "answers"}),
    ],
)
async def test_cualquier_fallo_devuelve_none(monkeypatch, handler):
    _mock_http(monkeypatch, handler)
    assert await jev_router.detect_routing_signals_jev("hola, quiero bucear") is None


async def test_tiempo_maximo_devuelve_none(monkeypatch):
    def handler(request):
        raise httpx.ReadTimeout("lento", request=request)

    _mock_http(monkeypatch, handler)
    assert await jev_router.detect_routing_signals_jev("hola, quiero bucear") is None


async def test_sin_clave_no_se_llama(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    assert await jev_router.detect_routing_signals_jev("hola, quiero bucear") is None


# --- Cascada por confianza (A/B del 24-sep) -------------------------------------------


def test_duda_con_los_numeros_reales_de_la_regresion():
    """"the discount of 10% is not showing up": Jev lo marcaba como problema en tiempo
    real con confianza 0,38 (y escalaba). Los problemas de pago reales van a 0,92-1,00."""
    regresion = {"sensitive_topic": {"type": "choice", "choice": "real_time_issues", "confidence": 0.38}}
    real = {"sensitive_topic": {"type": "choice", "choice": "real_time_issues", "confidence": 0.92}}
    assert jev_router.uncertain_answers(regresion)
    assert not jev_router.uncertain_answers(real)


def test_zona_de_duda_de_los_si_no_y_opciones_ignoradas():
    ans = {
        "availability_question": {"type": "noul", "noul": 0.45},
        "wants_human": {"type": "noul", "noul": 0.95},
        "opt_snorkel": {"type": "noul", "noul": 0.5},  # las opciones no cuentan
    }
    assert jev_router.uncertain_answers(ans) == ["availability_question@0.45"]
    assert not jev_router.uncertain_answers({"wants_human": {"type": "noul", "noul": 0.1}})


async def test_si_jev_duda_devuelve_uncertain(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"answers": {
            "sensitive_topic": {"type": "choice", "choice": "real_time_issues", "confidence": 0.38},
        }})

    _mock_http(monkeypatch, handler)
    got = await jev_router.detect_routing_signals_jev("the discount of 10% is not showing up")
    assert got == jev_router.UNCERTAIN


async def test_si_jev_duda_decide_el_router_llm(monkeypatch, llm, facts):
    async def _duda(message, *, lang="es"):
        return jev_router.UNCERTAIN

    monkeypatch.setattr(settings, "jev_router_enabled", True)
    monkeypatch.setattr(jev_router, "detect_routing_signals_jev", _duda)
    await escalation.detect_routing_signals("the discount of 10% is not showing up")
    assert llm.calls == 1
    assert facts["router"] == "llm_uncertain"
