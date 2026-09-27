"""Paso 5 (RAG, l1-6 + l1-7, 27-sep). Sonda de los 57 fallos de RAG de la ronda A en el contenedor
de PRE (`docs/robustness/paso5-rag/`):

- los atajos de precio por regex contestaban preguntas que no eran de precio ("¿Cuánto tiempo
  dura?" -> lista de precios) y el LLM contradecía reglas del catálogo que la búsqueda no traía
  (cursos de 2 días "ida y vuelta", el paquete de 3 inmersiones "en 1 día") -> flag `rag_v2`: el
  catálogo entero como hechos en el contexto;
- el juez de grounding mandaba al "no lo tengo a la mano" saludos y respuestas correctas -> juez v2;
- el texto fijo de disponibilidad se comía el resto del mensaje -> contesta el RAG;
- "2.215.000" era un "teléfono" y bloqueaba el mensaje por privacidad;
- la respuesta en paralelo de u3-4 se cancelaba en salidas que no la recogían.
"""

from __future__ import annotations

import asyncio

import pytest

from src.agents import conversational_core as core
from src.agents import grounding_check, rag_agent
from src.config import settings
from src.flows.catalog import OVERNIGHT_SERVICES, SERVICES, catalog_facts
from src.flows.state import ConversationState
from src.privacy import detect_pii, redact_pii
from src.utils import money


# ─── Catálogo como hechos ────────────────────────────────────────────────────

def _line(text: str, name: str) -> str:
    return next(line for line in text.splitlines() if line.startswith(f"- {name}:"))


def test_el_catalogo_dice_que_paquetes_y_cursos_obligan_a_dormir_en_las_islas():
    es = catalog_facts("es")
    for sid in ("3_dives_1_day", "5_dives_2_days", "open_water"):
        assert "dormir en las islas" in _line(es, SERVICES[sid]["name_es"])
    assert "ida y vuelta desde Cartagena el mismo día" in _line(es, SERVICES["2_dives_1_day"]["name_es"])
    assert "3_dives_1_day" in OVERNIGHT_SERVICES  # buceo nocturno: "debes alojarte 1 noche"
    assert "stay overnight" in _line(catalog_facts("en"), SERVICES["open_water"]["name_en"])


def test_los_precios_del_catalogo_salen_de_services_json():
    es = catalog_facts("es")
    svc = SERVICES["minicourse"]
    assert money.usd_cop(svc["price_usd"], svc["price_cop"]) in _line(es, svc["name_es"])
    assert "edad mínima 6" in _line(es, SERVICES["snorkeling"]["name_es"])
    assert "Acompañante (no bucea" in es


# ─── rag_answer con el flag ──────────────────────────────────────────────────

class _Resp:
    def __init__(self, content):
        msg = type("M", (), {"content": content})()
        self.choices = [type("C", (), {"message": msg})()]
        self.usage = type("U", (), {"total_tokens": 1})()


def _openai(respuesta: str, seen: list):
    class _Completions:
        async def create(self, **kwargs):
            seen.append(kwargs)
            return _Resp(respuesta)

    class _Cliente:
        def __init__(self, api_key=None):
            self.chat = type("Ch", (), {"completions": _Completions()})()

    return _Cliente


@pytest.fixture
def rag_offline(monkeypatch):
    seen: list = []

    async def _busqueda(*a, **k):
        return [{"content": "El Curso Basico PADI dura 2 dias.", "score": 0.99, "metadata": {"source": "faqs"}}]

    async def _sin_expandir(docs, lang="es"):
        return docs

    async def _sin_reescribir(query, history=None, lang="es"):
        return query

    async def _juez(answer, context, lang="es"):
        return True, "GROUNDED"

    monkeypatch.setattr(rag_agent, "search_knowledge_base", _busqueda)
    monkeypatch.setattr(rag_agent, "_expand_with_parent_context", _sin_expandir)
    monkeypatch.setattr(rag_agent, "condense_query", _sin_reescribir)
    monkeypatch.setattr(rag_agent, "is_grounded", _juez)

    def _set(respuesta):
        monkeypatch.setattr(rag_agent, "AsyncOpenAI", _openai(respuesta, seen))
        return seen

    return _set


async def test_cuanto_tiempo_dura_ya_no_recibe_la_lista_de_precios(monkeypatch, rag_offline):
    monkeypatch.setattr(settings, "rag_v2", True)
    seen = rag_offline("El curso dura 2 días y hay que dormir en las islas.")
    answer = await rag_agent.rag_answer("Cuánto tiempo dura ?", lang="es")
    assert answer.startswith("El curso dura 2 días")
    user = seen[0]["messages"][-1]["content"]
    assert "CATÁLOGO OFICIAL" in user


async def test_un_precio_del_catalogo_pasa_el_guard_de_importes(monkeypatch, rag_offline):
    monkeypatch.setattr(settings, "rag_v2", True)
    svc = SERVICES["open_water"]
    price = money.usd_cop(svc["price_usd"], svc["price_cop"])
    rag_offline(f"El Curso Básico PADI cuesta {price} por persona.")
    answer = await rag_agent.rag_answer("¿cuánto cuesta el curso básico?", lang="es")
    assert price in answer


async def test_sin_el_flag_sigue_el_atajo_de_precios(monkeypatch, rag_offline):
    monkeypatch.setattr(settings, "rag_v2", False)
    seen = rag_offline("no debería llamarse")
    answer = await rag_agent.rag_answer("Cuánto tiempo dura ?", lang="es")
    assert "precios de referencia" in answer and seen == []


# ─── Juez v2 ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("flag, prompt, model_attr", [
    (True, grounding_check.GROUNDING_VERIFY_V2_ES, "rag_answer_model"),
    (False, grounding_check.GROUNDING_VERIFY_ES, "openai_model"),
])
async def test_el_juez_usa_el_prompt_y_el_modelo_del_flag(monkeypatch, flag, prompt, model_attr):
    monkeypatch.setattr(settings, "rag_v2", flag)
    seen: list = []
    monkeypatch.setattr(grounding_check, "AsyncOpenAI", _openai("GROUNDED", seen))
    grounded, _ = await grounding_check.is_grounded("Hola, soy Coral 🪸", "contexto", lang="es")
    assert grounded
    assert seen[0]["messages"][0]["content"] == prompt
    assert seen[0]["model"] == getattr(settings, model_attr)


# ─── Disponibilidad ──────────────────────────────────────────────────────────

def _state(**kw) -> ConversationState:
    s = ConversationState(conversation_id="rag-v2")
    s.language = "es"
    for k, v in kw.items():
        setattr(s, k, v)
    return s


async def test_la_pregunta_de_disponibilidad_sigue_al_rag_con_el_flag(monkeypatch):
    monkeypatch.setattr(settings, "rag_v2", True)
    msg = "¿Tienen disponibilidad el 6 de febrero? ¿Las fotos tienen precio adicional?"
    assert await core._availability_phase(_state(), msg, {}, "") is None


async def test_los_dias_cerrados_se_siguen_contestando_con_la_politica(monkeypatch):
    monkeypatch.setattr(settings, "rag_v2", True)
    reply = await core._availability_phase(_state(), "¿abren el 25 de diciembre?", {}, "")
    assert reply and "diciembre" in reply.lower()


# ─── Privacidad ──────────────────────────────────────────────────────────────

def test_un_precio_en_cop_no_es_un_telefono():
    msg = "Con tarjeta de crédito son los mismos 2.215.000?"
    assert detect_pii(msg) == []
    assert redact_pii(msg) == msg
    assert redact_pii("entre 1.429.000 y 2.170.000") == "entre 1.429.000 y 2.170.000"


def test_telefonos_y_documentos_se_siguen_detectando():
    assert "phone" in detect_pii("llámame al 320 231 5150")
    assert "phone" in detect_pii("tel 300.123.4567")
    assert "id_or_account" in detect_pii("mi cédula es 1.023.456.789")
    assert "payment_card" in detect_pii("mi tarjeta es 4111 1111 1111 1111")
    assert "[REDACTED_NUMBER]" in redact_pii("mi cédula es 1.023.456.789")


# ─── Respuesta en paralelo sin recoger ───────────────────────────────────────

async def test_una_respuesta_en_paralelo_sin_recoger_va_delante():
    st = _state()
    st._pending_answer = asyncio.ensure_future(asyncio.sleep(0, result="Sí, operamos el Domingo de Pascua."))
    reply = await core.attach_unused_answer(st, "Esto es lo que tengo hasta ahora: 🤿")
    assert reply == "Sí, operamos el Domingo de Pascua.\n\nEsto es lo que tengo hasta ahora: 🤿"
    assert st._pending_answer is None


async def test_sin_respuesta_pendiente_no_cambia_nada():
    st = _state()
    assert await core.attach_unused_answer(st, "hola") == "hola"


def test_el_paquete_de_3_inmersiones_obliga_a_dormir():
    assert core._plan_needs_overnight(_state(detected_service_id="3_dives_1_day"))


# ─── Juez v3 (flag `grounding_v3`) ───────────────────────────────────────────

def test_el_veredicto_v3_sale_de_las_marcas_de_cada_dato():
    assert not grounding_check.verdict_from_fact_list("- Llevamos 30 años en las islas. NO  \n\nHALLUCINATED")
    assert grounding_check.verdict_from_fact_list("- Paquete de 5: 392 USD: SÍ\n\nGROUNDED")
    # sin datos del negocio es GROUNDED aunque el modelo se contradiga en la última línea
    assert grounding_check.verdict_from_fact_list("- (ninguno)\nHALLUCINATED")
    assert not grounding_check.verdict_from_fact_list("- Hay barcos hundidos: NO.\nGROUNDED")


async def test_el_juez_v3_usa_su_prompt_y_modelo(monkeypatch):
    monkeypatch.setattr(settings, "rag_v2", True)
    monkeypatch.setattr(settings, "grounding_v3", True)
    seen: list = []
    monkeypatch.setattr(grounding_check, "AsyncOpenAI", _openai("- Llevamos 30 años: NO\nHALLUCINATED", seen))
    grounded, reason = await grounding_check.is_grounded("Llevamos 30 años", "contexto", lang="es")
    assert not grounded and "30 años" in reason
    assert seen[0]["messages"][0]["content"] == grounding_check.GROUNDING_VERIFY_V3_ES
    assert seen[0]["model"] == settings.grounding_v3_model
