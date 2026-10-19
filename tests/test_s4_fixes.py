"""Paso 6 (27-sep; el flag `s4_fixes` se quitó en s4-25): salida y flujo deterministas de S4.

- s4-14: si piden un teléfono, el WhatsApp oficial (de la base de conocimiento), decisión de Gadea.
- s4-15: "¿eres un bot?" -> dice que es la asistente virtual.
- s4-16: la queja pasa a staff con una disculpa.
- s4-21: nunca un id interno en el resumen; el aviso sensible en el idioma del mensaje de apertura;
  un acuse sin prosa ('{" "}') se descarta.
- s4-7: "¿cómo pago?" -> el link de reserva, no "un asesor te enviará el enlace".
- s4-20: post-venta y empresa (Jev `needs_staff`) -> una persona, antes del núcleo.
- s4-6: cambio de fecha con el carrito abierto (Jev `changes_date`) -> política + asesor.
"""

from __future__ import annotations

import pytest

from src.agents import escalation, jev_router, supervisor
from src.agents import rag_agent
from src.config import settings
from src.domain import activities as dom
from src.flows.state import ConversationState
from src.orchestration import router
from src.prompts import info


@pytest.fixture(autouse=True)
def _camino_antiguo_ex2_ex3(monkeypatch):
    """Estos tests fijan el camino de antes de ex-2/ex-3 (lista entera de palabras clave y respuestas fijas); lo nuevo
    lo cubren tests/test_ex2_escalado.py y tests/test_ex3_atajos.py."""
    from src.config import settings as _flags

    monkeypatch.setattr(_flags, "escalado_solo_emergencias", False)
    monkeypatch.setattr(_flags, "atajo_resumen_por_rag", False)
    monkeypatch.setattr(_flags, "atajo_nacionalidad_por_rag", False)


def _state(**kw) -> ConversationState:
    s = ConversationState(conversation_id="s4")
    s.language = "es"
    for k, v in kw.items():
        setattr(s, k, v)
    return s


# ─── Respuestas fijas ────────────────────────────────────────────────────────

def test_si_piden_telefono_NO_se_da_el_numero(monkeypatch):
    """DECISIÓN DE GADEA del 16-oct, que sustituye a la del 17-sep (dar el WhatsApp oficial): esto es un chatbot y no
    da números; quien pide un contacto directo pasa con un asesor (`contacto_pasa_a_persona`, flag de CAL-E1)."""
    monkeypatch.setattr(settings, "contacto_pasa_a_persona", True)
    assert "+57" not in supervisor._contact_number_deflection("es")
    assert "+57" not in supervisor._contact_number_deflection("en")


def test_con_el_flag_apagado_se_da_el_whatsapp_como_antes(monkeypatch):
    """El camino de antes sigue entero: es el revert si la ronda del golden no sostiene el cambio."""
    monkeypatch.setattr(settings, "contacto_pasa_a_persona", False)
    number = supervisor._official_whatsapp()
    assert number and number.startswith("+57")
    assert number in supervisor._contact_number_deflection("es")
    assert number in supervisor._contact_number_deflection("en")


def test_eres_un_bot_dice_que_es_la_asistente_virtual():
    assert "asistente virtual" in supervisor._ai_identity_deflection("es")
    assert "virtual assistant" in supervisor._ai_identity_deflection("en")


def test_la_queja_pasa_a_staff_con_una_disculpa():
    _, text = escalation.sensitive_response_for("complaints_or_emergencies", "es")
    assert "Siento mucho" in text and "staff" in text
    _, text = escalation.detect_sensitive_escalation("this is a scam, I want my money back", "en")
    assert "sorry" in text.lower()


# ─── s4-21 ───────────────────────────────────────────────────────────────────

def test_un_resumen_nunca_muestra_un_id_interno():
    for act in dom.activity_ids():
        for lang in ("es", "en"):
            text = dom.text(act, "recall", lang, default=act)
            assert text and "_" not in text, (act, lang, text)


def test_el_aviso_sensible_sale_en_el_idioma_del_mensaje_de_apertura():
    st = _state()
    assert supervisor._reply_language(st, "I completed the medical form, is that ok?") == "en"
    assert supervisor._reply_language(st, "tengo asma, ¿puedo bucear?") == "es"
    st.detected_language = "es"
    assert supervisor._reply_language(st, "I have asthma") == "es"  # ya fijado: se respeta


async def test_un_acuse_sin_prosa_se_descarta(monkeypatch):
    from src.agents import llm_extractor

    class _Msg:
        content = '{" "}'

    class _Resp:
        choices = [type("C", (), {"message": _Msg()})()]

    class _Cli:
        def __init__(self, *a, **k):
            async def create(**kw):
                return _Resp()
            self.chat = type("Ch", (), {"completions": type("Co", (), {"create": staticmethod(create)})()})()

    monkeypatch.setattr(llm_extractor, "AsyncOpenAI", _Cli)
    monkeypatch.setattr(llm_extractor, "trace_openai", lambda c: c)
    assert await llm_extractor.compose_acknowledgement("somos 4", lang="es") == ""


# ─── s4-7 ────────────────────────────────────────────────────────────────────

def test_el_prompt_manda_al_link_de_reserva():
    """Las viñetas de pago de s4-7 están escritas en el cuerpo del prompt (antes las sustituía el flag)."""
    for lang, nueva, vieja in (
        ("es", "NUNCA digas que un asesor enviará el enlace de pago", "di que el asesor le enviará el enlace"),
        ("en", "NEVER say that an advisor will send the payment link", "the advisor will send the correct link"),
    ):
        prompt = rag_agent.build_system_prompt(lang)
        assert nueva in prompt and vieja not in prompt
        assert nueva in (info.RAG_BODY_ES if lang == "es" else info.RAG_BODY_EN)


# ─── s4-20 y s4-6: preguntas de Jev ──────────────────────────────────────────

def test_las_preguntas_nuevas_van_siempre():
    q = jev_router._questions_for_turn()
    assert jev_router.NEEDS_STAFF in q and jev_router.CHANGES_DATE in q
    out = jev_router.answers_to_signals({"needs_staff": {"noul": 0.9}, "changes_date": {"noul": 0.2}})
    assert out["needs_staff"] is True and out["changes_date"] is False


def test_post_venta_pasa_a_una_persona():
    st = _state()
    reply = supervisor._needs_staff_handoff(st, "ya hice la reserva, ¿la recibieron?", {"needs_staff": True})
    assert reply and "asesor" in reply
    assert st.pending_escalation_reason and st.step.value == "escalate"
    assert supervisor._needs_staff_handoff(_state(), "hola", {"needs_staff": False}) is None


def test_post_venta_va_al_nodo_de_escalado():
    assert router.classify_route(_state(), "¿está todo ok con mis reservas?", {"needs_staff": True}) == router.ROUTE_SAFETY


def test_cambio_de_fecha_con_el_carrito_abierto_va_a_cambios(monkeypatch):
    st = _state(detected_activity="snorkel", detected_group_size=3, location="cartagena")
    monkeypatch.setattr(supervisor, "_in_active_cart_building", lambda s: True)
    signals = {"booking_change_topic": "reschedule", "changes_date": True}
    assert router.classify_route(st, "espera, mejor cambiemos la fecha", signals) == router.ROUTE_CHANGE
    # sin la pregunta de Jev, la señal del router sigue sin valer con el carrito abierto
    assert router.classify_route(st, "hazlo para 3 días", {"booking_change_topic": "reschedule"}) != router.ROUTE_CHANGE


async def test_el_rag_tiene_los_links_de_reserva(monkeypatch):
    """Ronda B del paso 6: "no sé cómo se haga la reserva" acababa en "no lo tengo" porque el LLM
    escribía un link que no estaba en el contexto y el guard de URLs lo rechazaba."""
    from src.flows.catalog import SERVICES

    seen = []

    async def _no_docs(*a, **k):
        return []

    async def _same(q, history=None, lang="es", hechos=None):
        return q

    class _Resp:
        def __init__(self, text):
            msg = type("M", (), {"content": text})()
            self.choices = [type("C", (), {"message": msg})()]
            self.usage = type("U", (), {"total_tokens": 1})()

    url = SERVICES["2_dives_1_day"]["booking_url"]

    class _Cli:
        def __init__(self, *a, **k):
            async def create(**kw):
                seen.append(kw)
                return _Resp(f"Reservas aquí: {url}")
            self.chat = type("Ch", (), {"completions": type("Co", (), {"create": staticmethod(create)})()})()

    async def _judge(answer, context, lang="es"):
        return True, "GROUNDED"

    monkeypatch.setattr(rag_agent, "search_knowledge_base", _no_docs)
    monkeypatch.setattr(rag_agent, "condense_query", _same)
    monkeypatch.setattr(rag_agent, "AsyncOpenAI", _Cli)
    monkeypatch.setattr(rag_agent, "is_grounded", _judge)
    answer = await rag_agent.rag_answer("¿cómo hago la reserva?", lang="es", extra_context="Cliente certificado.")
    assert url in answer


async def test_tras_el_pase_a_una_persona_un_gracias_no_vuelve_a_vender(monkeypatch):
    from src.agents import conversational_core as core
    from src.flows.state import Step

    # La cortesía de s4-20 (con `tras_pase_sin_vender` cualquier turno tras el pase se atiende sin vender:
    # tests/test_tras_el_pase.py).
    monkeypatch.setattr(core.settings, "tras_pase_sin_vender", False)

    st = _state(step=Step.ESCALATE)
    quiet = {"asks_question": False, "needs_staff": False, "affirms_location": False, "affirms_activity": False}
    reply = await core._availability_phase(st, "gracias", quiet, "")
    assert reply and "asesor" in reply and "animas" not in reply
    # si pregunta algo, o Jev no contestó, sigue el turno normal
    assert await core._availability_phase(_state(step=Step.ESCALATE), "¿y a qué hora?", {**quiet, "asks_question": True}, "") is None
    assert await core._availability_phase(_state(step=Step.ESCALATE), "gracias", {}, "") is None


def test_ida_y_vuelta_solo_si_se_sabe_que_el_plan_es_de_un_dia():
    from src.agents import conversational_core as core

    generic = _state(detected_activity="padi_course")
    assert not core._plan_is_single_day(generic)
    assert "mismo día" not in core.ask_slot(generic, core.SLOT_LOCATION)
    assert "mismo día" not in core.ask_slot(_state(), core.SLOT_LOCATION)
    mini = _state(detected_activity="minicourse")
    assert core._plan_is_single_day(mini)
    assert "ida y vuelta el mismo día" in core.ask_slot(mini, core.SLOT_LOCATION)


def test_el_catalogo_dice_si_el_almuerzo_va_incluido():
    from src.flows.catalog import SERVICES, catalog_facts

    es = catalog_facts("es")
    island = next(l for l in es.splitlines() if l.startswith(f"- {SERVICES['minicourse_already_on_island']['name_es']}:"))
    cartagena = next(l for l in es.splitlines() if l.startswith(f"- {SERVICES['minicourse']['name_es']}:"))
    assert "almuerzo NO incluido" in island and "almuerzo incluido" in cartagena


async def test_corregir_el_precio_que_cita_el_cliente_no_acaba_en_no_lo_tengo(monkeypatch):
    """Ronda B del paso 6: "¿con tarjeta son los mismos 2.215.000?" -> la corrección nombra su cifra."""
    async def _docs(*a, **k):
        return [{"content": "Curso Basico PADI: 2.450.000 COP online.", "score": 0.99, "metadata": {"source": "faqs"}}]

    async def _same(q, history=None, lang="es", hechos=None):
        return q

    async def _docs_back(docs, lang="es"):
        return docs

    async def _judge(answer, context, lang="es"):
        return True, "GROUNDED"

    class _Resp:
        def __init__(self, text):
            msg = type("M", (), {"content": text})()
            self.choices = [type("C", (), {"message": msg})()]
            self.usage = type("U", (), {"total_tokens": 1})()

    class _Cli:
        def __init__(self, *a, **k):
            async def create(**kw):
                return _Resp("El precio online es 2.450.000 COP, no 2.215.000 COP.")
            self.chat = type("Ch", (), {"completions": type("Co", (), {"create": staticmethod(create)})()})()

    monkeypatch.setattr(rag_agent, "search_knowledge_base", _docs)
    monkeypatch.setattr(rag_agent, "_expand_with_parent_context", _docs_back)
    monkeypatch.setattr(rag_agent, "condense_query", _same)
    monkeypatch.setattr(rag_agent, "AsyncOpenAI", _Cli)
    monkeypatch.setattr(rag_agent, "is_grounded", _judge)
    answer = await rag_agent.rag_answer("Con tarjeta de crédito son los mismos 2.215.000 COP?", lang="es")
    assert "2.450.000" in answer


def test_el_curso_referido_duerme_en_las_islas():
    """Decisión de Gadea (14-oct): el Curso Referido, como el Open Water, duerme en las islas el día 1 (antes la base
    decía que se podía volver a Cartagena y la política de los cursos de 2 días decía lo contrario: el RAG se
    contradecía). services.json lo marca con "overnight": "required"."""
    from src.agents import conversational_core as core
    from src.flows.catalog import OVERNIGHT_SERVICES, catalog_facts

    assert "referral" in OVERNIGHT_SERVICES and "mindful_diving" in OVERNIGHT_SERVICES
    st = _state(detected_activity="padi_open_water_referral")
    assert core._plan_needs_overnight(st) and not core._plan_is_single_day(st)
    assert "mismo día" not in core.ask_slot(st, core.SLOT_LOCATION)
    assert "puedes volver a Cartagena o dormir en las islas" not in catalog_facts("es")
