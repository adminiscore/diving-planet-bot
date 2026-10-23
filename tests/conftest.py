"""Shared test fixtures.

Con el núcleo conversacional como único camino (Fase 4), el orquestador legacy
se retiró; solo queda el stub offline de RAG (`_rag_answers_offline`) para que los
tests de flujo de conversación no peguen al pipeline real.
"""


import os

import pytest

# 17-oct: los tests que montan el RAG de verdad (búsqueda y LLM de mentira) CREAN el cliente de OpenAI, y sin clave en
# el entorno el SDK falla al crearlo ("Missing credentials"): 8 tests del RAG fallaban al pasar la suite sin ENV_FILE.
# CI usa `.env.ci`, que trae una clave de mentira; aquí se hace lo mismo, solo si no se ha elegido un ENV_FILE (los
# tests `live` con `.env.dev` siguen usando la clave de verdad: una variable de entorno le ganaría al fichero).
if not os.environ.get("ENV_FILE"):
    os.environ.setdefault("OPENAI_API_KEY", "sk-test-sin-clave")

# Canned RAG answer for the default offline mock (see _rag_answers_offline below).
_RAG_STUB = "rag_answer_stub"

# Modules that legitimately exercise the real RAG pipeline (grounding, retrieval,
# fallback) and must NOT get the offline stub. test_rag_safety calls
# rag_agent.rag_answer directly (a different ref than supervisor.rag_answer, so
# it's unaffected anyway) but is listed for clarity; the FreeText/* suite is
# integration/live by nature.
_RAG_LIVE_MODULES = {"test_rag_safety"}

@pytest.fixture(autouse=True)
def _rag_answers_offline(request, monkeypatch):
    """Default: stub `supervisor.rag_answer` so conversation-flow tests that fall
    through to answer_question don't hit the real RAG LLM (slow + non-deterministic
    grounding → the source of flaky failures like test_go_pro_itinerary_back).

    A test that needs specific RAG behavior overrides this with its own
    `patch("src.agents.supervisor.rag_answer", ...)` (applied inside the test, so
    it wins). Modules in _RAG_LIVE_MODULES and any test marked `@pytest.mark.live`
    opt out and see the real pipeline.
    """
    module = request.node.module.__name__.rsplit(".", 1)[-1]
    if module in _RAG_LIVE_MODULES or request.node.get_closest_marker("live"):
        return

    from src.agents import supervisor

    async def _stub_rag(message, **kwargs):
        return _RAG_STUB

    monkeypatch.setattr(supervisor, "rag_answer", _stub_rag)


@pytest.fixture(autouse=True)
def _no_typing_indicator(request, monkeypatch):
    """l2-3: el "escribiendo…" llama a la API de Chatwoot en cada mensaje. En los tests se
    anula para no tocar la red; tests/test_typing_indicator.py lo prueba de verdad."""
    if request.node.module.__name__.rsplit(".", 1)[-1] == "test_typing_indicator":
        return
    from src.channels import chatwoot

    async def _noop(conversation_id, on):
        return None

    monkeypatch.setattr(chatwoot, "set_typing", _noop)


@pytest.fixture(autouse=True)
def _no_llm_language_fallback(monkeypatch):
    """Default the welcome-step LLM language fallback (conversational_core →
    language_detector.detect_language_llm) to "no detection", so tests stay
    deterministic and never hit the network regardless of a local OPENAI_API_KEY.
    A test that exercises the fallback overrides this with its own patch."""

    async def _no_detect(message):
        return None

    monkeypatch.setattr("src.agents.language_detector.detect_language_llm", _no_detect)




@pytest.fixture(autouse=True)
def _sin_aviso_de_openai_caido(monkeypatch, request):
    """r6-1(b): el aviso de OpenAI caído va siempre (su flag `aviso_si_openai_falla` se borró en sim-5), pero aquí la
    clave de OpenAI es falsa y todas las llamadas fallan (401): el aviso saltaría en cada turno y taparía lo que mide
    cada test. Aquí ningún turno cuenta como OpenAI caído, salvo en los tests del aviso
    (test_r61_tiempos_por_llamada.py)."""
    if "test_r61_tiempos_por_llamada" in request.node.nodeid:
        return
    monkeypatch.setattr("src.observability.fallo_de_openai_en_el_turno", lambda: None)


@pytest.fixture
def extractor_dice(monkeypatch):
    """ex-9b paso 3: simula el extractor del turno con lo que el cliente AFIRMA en cada mensaje, como el oráculo del
    replay del estudio (`parte5`). En los tests no hay red: sin esto el extractor falla siempre y el turno va por la
    rama "el extractor falló" (sin la pista del regex: el dato se pregunta y, a los dos fallos seguidos, se pasa a un
    asesor), que no es el camino de producción.

    Uso: `extractor_dice({"somos 3 para snorkel": {"activity": "snorkel", "group_size": 3}, ...})`, con los datos tal
    como los devuelve `extractor_turno.extraer_turno` (ya con sus reglas). Un mensaje que no está = el extractor leyó y
    el mensaje no afirma nada ({}). Se puede llamar varias veces (se suma). Se simula la llamada al modelo, así que el
    turno corre entero: la extracción adelantada del enrutador, `datos_del_extractor` y lo dicho en el pase. Los datos
    los escribe cada test; nunca salen del regex del detector (escondería lo que lee el extractor)."""
    import copy

    from src.agents import extractor_turno

    oraculo: dict[str, dict] = {}

    async def _extraer_turno(mensaje, **_kw):
        return copy.deepcopy(oraculo.get((mensaje or "").strip(), {}))

    monkeypatch.setattr(extractor_turno, "extraer_turno", _extraer_turno)
    return lambda datos_por_mensaje: oraculo.update({m.strip(): d for m, d in datos_por_mensaje.items()})
